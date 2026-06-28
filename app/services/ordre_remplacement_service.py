# backend/app/services/ordre_remplacement_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging

from ..models.ordre_remplacement import OrdreRemplacement, StatutOrdreRemplacement, PrioriteOrdre
from ..models.bien import Bien
from ..models.alerte_vnc import AlerteVNC, StatutAlerteVNC
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..models.notification import TypeNotificationEnum
from ..services.notification_service import NotificationService
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class OrdreRemplacementService:
    """
    Service de gestion des ordres de remplacement des immobilisations.
    Gère le cycle de vie complet des ordres de remplacement :
    - Création automatique suite à une alerte VNC
    - Attribution aux responsables (DG, Comptable)
    - Suivi et validation
    - Exécution et clôture
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.audit_service = AuditService(db)

    def creer_ordre(
        self,
        bien_id: int,
        motif: str,
        alerte_id: Optional[int] = None,
        priorite: Optional[str] = None,
        utilisateur_id: Optional[int] = None
    ) -> OrdreRemplacement:
        """
        Crée un ordre de remplacement pour le DG et le Comptable.
        
        Args:
            bien_id: ID du bien à remplacer
            motif: Motif du remplacement
            alerte_id: ID de l'alerte VNC associée (optionnel)
            priorite: Priorité de l'ordre (optionnel)
            utilisateur_id: ID de l'utilisateur créateur (optionnel)
        
        Returns:
            OrdreRemplacement: L'ordre créé
        """
        # Vérifier que le bien existe
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")
        
        # Vérifier qu'un ordre n'existe pas déjà pour ce bien
        ordre_existant = self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.bien_id == bien_id,
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS,
                StatutOrdreRemplacement.VALIDE
            ])
        ).first()
        
        if ordre_existant:
            raise ValueError(f"Un ordre de remplacement existe déjà pour le bien {bien_id} (statut: {ordre_existant.statut.value})")
        
        # Déterminer la priorité
        if not priorite:
            if bien.est_critique:
                priorite = PrioriteOrdre.CRITIQUE.value
            else:
                priorite = PrioriteOrdre.NORMALE.value
        
        # Récupérer les informations du bien
        designation = self._get_bien_designation(bien)
        prix_acquisition = float(bien.prix_acquisition or 0)
        vnc = bien.valeur_nette_comptable
        
        # Créer l'ordre
        ordre = OrdreRemplacement(
            bien_id=bien_id,
            alerte_vnc_id=alerte_id,
            motif=motif,
            priorite=priorite,
            statut=StatutOrdreRemplacement.EN_ATTENTE,
            designation_bien=designation,
            prix_acquisition=prix_acquisition,
            vnc_actuelle=vnc,
            date_creation=datetime.utcnow(),
            date_echeance=self._calculer_date_echeance(priorite, bien.est_critique),
            cree_par_id=utilisateur_id
        )
        
        self.db.add(ordre)
        self.db.commit()
        self.db.refresh(ordre)
        
        # Si une alerte VNC est associée, la mettre à jour
        if alerte_id:
            alerte = self.db.query(AlerteVNC).filter(AlerteVNC.id == alerte_id).first()
            if alerte:
                alerte.statut = StatutAlerteVNC.EN_COURS
                self.db.commit()
        
        # Journaliser la création
        self.audit_service.log_action(
            user_id=utilisateur_id,
            table_name="ordres_remplacement",
            record_id=ordre.id,
            action="CREATE",
            nouvelles_valeurs={
                "bien_id": bien_id,
                "motif": motif,
                "priorite": priorite,
                "statut": ordre.statut.value
            }
        )
        
        # Envoyer les notifications
        self._notifier_creation_ordre(ordre)
        
        logger.info(f"Ordre de remplacement créé pour le bien {bien_id} - Motif: {motif}")
        return ordre

    def _calculer_date_echeance(self, priorite: str, est_critique: bool) -> datetime:
        """Calcule la date d'échéance en fonction de la priorité"""
        now = datetime.utcnow()
        
        if priorite == PrioriteOrdre.CRITIQUE.value:
            return now + timedelta(days=7)  # 7 jours pour les critiques
        elif priorite == PrioriteOrdre.URGENT.value:
            return now + timedelta(days=15)  # 15 jours pour les urgents
        elif priorite == PrioriteOrdre.NORMALE.value:
            return now + timedelta(days=30)  # 30 jours pour les normaux
        else:
            return now + timedelta(days=45)  # 45 jours par défaut

    def _get_bien_designation(self, bien: Bien) -> str:
        """Récupère la désignation d'un bien"""
        if hasattr(bien, 'marque') and bien.marque:
            designation = f"{bien.marque} {getattr(bien, 'modele', '')}".strip()
            return designation or f"Bien #{bien.id_bien}"
        elif hasattr(bien, 'fabricant') and bien.fabricant:
            designation = f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip()
            return designation or f"Bien #{bien.id_bien}"
        return bien.description or f"Bien #{bien.id_bien}"

    def _notifier_creation_ordre(self, ordre: OrdreRemplacement):
        """Notifie les responsables de la création d'un ordre"""
        # Récupérer la désignation du bien
        bien = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
        designation = ordre.designation_bien or f"Bien #{ordre.bien_id}"
        
        # Titre et contenu selon la priorité
        if ordre.priorite == PrioriteOrdre.CRITIQUE.value:
            titre = f"🚨 ORDRE CRITIQUE - Remplacement requis : {designation}"
            contenu = f"Le bien {designation} a atteint son seuil de sécurité VNC. Remplacement URGENT requis. VNC: {ordre.vnc_actuelle:.2f} FCFA"
        elif ordre.priorite == PrioriteOrdre.URGENT.value:
            titre = f"⚠️ ORDRE URGENT - Remplacement requis : {designation}"
            contenu = f"Le bien {designation} nécessite un remplacement rapide. VNC: {ordre.vnc_actuelle:.2f} FCFA"
        else:
            titre = f"📋 Ordre de remplacement - {designation}"
            contenu = f"Le bien {designation} doit être remplacé. VNC: {ordre.vnc_actuelle:.2f} FCFA"
        
        contenu += f"\nMotif: {ordre.motif}"
        contenu += f"\nÉchéance: {ordre.date_echeance.strftime('%d/%m/%Y') if ordre.date_echeance else 'Non définie'}"
        
        # Notifier le DG
        self.notification_service.envoyer_notification_par_role(
            role_nom="DG",
            type_notif=TypeNotificationEnum.ALERTE_VNC_ZERO,
            titre=titre,
            contenu=contenu,
            lien=f"/ordres-remplacement/{ordre.id}"
        )
        
        # Notifier le Comptable
        self.notification_service.envoyer_notification_par_role(
            role_nom="COMPTABLE",
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"💰 {titre}",
            contenu=contenu,
            lien=f"/ordres-remplacement/{ordre.id}"
        )
        
        # Notifier l'Administrateur
        self.notification_service.envoyer_notification_par_role(
            role_nom="ADMIN",
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"📋 {titre}",
            contenu=f"Un ordre de remplacement a été créé pour le bien {designation}. Veuillez suivre le traitement.",
            lien=f"/ordres-remplacement/{ordre.id}"
        )

    def get_ordre(self, ordre_id: int) -> Optional[OrdreRemplacement]:
        """Récupère un ordre par son ID"""
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.id == ordre_id
        ).first()

    def get_ordres_par_bien(self, bien_id: int) -> List[OrdreRemplacement]:
        """Récupère tous les ordres pour un bien donné"""
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.bien_id == bien_id
        ).order_by(OrdreRemplacement.date_creation.desc()).all()

    def get_ordres_en_attente(self, limit: int = 50) -> List[OrdreRemplacement]:
        """Récupère les ordres en attente de traitement"""
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EN_ATTENTE
        ).order_by(OrdreRemplacement.date_echeance.asc()).limit(limit).all()

    def get_ordres_en_cours(self, limit: int = 50) -> List[OrdreRemplacement]:
        """Récupère les ordres en cours de traitement"""
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EN_COURS
        ).order_by(OrdreRemplacement.date_creation.desc()).limit(limit).all()

    def get_ordres_urgents(self) -> List[OrdreRemplacement]:
        """Récupère les ordres urgents et critiques"""
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS
            ]),
            OrdreRemplacement.priorite.in_([
                PrioriteOrdre.CRITIQUE.value,
                PrioriteOrdre.URGENT.value
            ])
        ).order_by(OrdreRemplacement.date_echeance.asc()).all()

    def get_ordres_en_retard(self) -> List[OrdreRemplacement]:
        """Récupère les ordres en retard (échéance dépassée)"""
        now = datetime.utcnow()
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS
            ]),
            OrdreRemplacement.date_echeance < now,
            OrdreRemplacement.date_echeance.isnot(None)
        ).order_by(OrdreRemplacement.date_echeance.asc()).all()

    def valider_ordre(
        self,
        ordre_id: int,
        utilisateur_id: int,
        bien_remplacement_id: Optional[int] = None,
        observations: Optional[str] = None
    ) -> OrdreRemplacement:
        """
        Valide un ordre de remplacement.
        """
        ordre = self.get_ordre(ordre_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")
        
        if ordre.statut != StatutOrdreRemplacement.EN_ATTENTE:
            raise ValueError(f"Impossible de valider un ordre en statut {ordre.statut.value}")
        
        # Vérifier que l'utilisateur a les droits (DG ou Comptable)
        utilisateur = self.db.query(Utilisateur).filter(Utilisateur.id == utilisateur_id).first()
        if not utilisateur:
            raise ValueError(f"Utilisateur {utilisateur_id} non trouvé")
        
        roles = [r.nom for r in utilisateur.roles]
        if not any(r in ["DG", "COMPTABLE", "ADMIN"] for r in roles):
            raise ValueError("Seul le DG, le Comptable ou l'Admin peut valider un ordre")
        
        # Mettre à jour l'ordre
        ordre.statut = StatutOrdreRemplacement.VALIDE
        ordre.date_validation = datetime.utcnow()
        ordre.valide_par_id = utilisateur_id
        ordre.bien_remplacement_id = bien_remplacement_id
        ordre.observations = observations
        
        self.db.commit()
        self.db.refresh(ordre)
        
        # Journaliser la validation
        self.audit_service.log_action(
            user_id=utilisateur_id,
            table_name="ordres_remplacement",
            record_id=ordre_id,
            action="VALIDE",
            nouvelles_valeurs={
                "statut": ordre.statut.value,
                "bien_remplacement_id": bien_remplacement_id
            }
        )
        
        # Notifier le DG et le Comptable
        bien = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
        designation = ordre.designation_bien or f"Bien #{ordre.bien_id}"
        
        self.notification_service.envoyer_notification_par_role(
            role_nom="DG",
            type_notif=TypeNotificationEnum.BESOIN_VALIDE,
            titre=f"✅ Ordre validé - {designation}",
            contenu=f"L'ordre de remplacement pour le bien {designation} a été validé par {utilisateur.nom}.",
            lien=f"/ordres-remplacement/{ordre.id}"
        )
        
        logger.info(f"Ordre {ordre_id} validé par l'utilisateur {utilisateur_id}")
        return ordre

    def executer_ordre(
        self,
        ordre_id: int,
        utilisateur_id: int,
        bien_remplacement_id: int,
        observations: Optional[str] = None
    ) -> OrdreRemplacement:
        """
        Exécute un ordre de remplacement (remplacement effectué).
        """
        ordre = self.get_ordre(ordre_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")
        
        if ordre.statut not in [StatutOrdreRemplacement.EN_ATTENTE, StatutOrdreRemplacement.VALIDE]:
            raise ValueError(f"Impossible d'exécuter un ordre en statut {ordre.statut.value}")
        
        # Vérifier que le bien de remplacement existe
        bien_remplacement = self.db.query(Bien).filter(Bien.id_bien == bien_remplacement_id).first()
        if not bien_remplacement:
            raise ValueError(f"Bien de remplacement {bien_remplacement_id} non trouvé")
        
        # Mettre à jour l'ordre
        ordre.statut = StatutOrdreRemplacement.EXECUTE
        ordre.date_execution = datetime.utcnow()
        ordre.execute_par_id = utilisateur_id
        ordre.bien_remplacement_id = bien_remplacement_id
        if observations:
            ordre.observations = (ordre.observations or "") + f"\nExécution: {observations}"
        
        # Mettre à jour le bien original
        bien_original = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
        if bien_original:
            bien_original.statut_comptable = "CEDE"
            bien_original.date_sortie = datetime.utcnow()
            bien_original.actif_remplacement_id = bien_remplacement_id
            self.db.commit()
        
        self.db.commit()
        self.db.refresh(ordre)
        
        # Journaliser l'exécution
        self.audit_service.log_action(
            user_id=utilisateur_id,
            table_name="ordres_remplacement",
            record_id=ordre_id,
            action="EXECUTE",
            nouvelles_valeurs={
                "statut": ordre.statut.value,
                "bien_remplacement_id": bien_remplacement_id
            }
        )
        
        # Notifier
        self.notification_service.envoyer_alerte_remplacement(
            bien_id=ordre.bien_id,
            bien_nouveau_id=bien_remplacement_id
        )
        
        logger.info(f"Ordre {ordre_id} exécuté avec le bien de remplacement {bien_remplacement_id}")
        return ordre

    def rejeter_ordre(
        self,
        ordre_id: int,
        utilisateur_id: int,
        motif_rejet: str
    ) -> OrdreRemplacement:
        """
        Rejette un ordre de remplacement.
        """
        ordre = self.get_ordre(ordre_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")
        
        if ordre.statut != StatutOrdreRemplacement.EN_ATTENTE:
            raise ValueError(f"Impossible de rejeter un ordre en statut {ordre.statut.value}")
        
        ordre.statut = StatutOrdreRemplacement.REJETE
        ordre.date_rejet = datetime.utcnow()
        ordre.rejete_par_id = utilisateur_id
        ordre.motif_rejet = motif_rejet
        
        self.db.commit()
        self.db.refresh(ordre)
        
        # Journaliser le rejet
        self.audit_service.log_action(
            user_id=utilisateur_id,
            table_name="ordres_remplacement",
            record_id=ordre_id,
            action="REJETE",
            nouvelles_valeurs={
                "statut": ordre.statut.value,
                "motif_rejet": motif_rejet
            }
        )
        
        logger.info(f"Ordre {ordre_id} rejeté par l'utilisateur {utilisateur_id}")
        return ordre

    def annuler_ordre(
        self,
        ordre_id: int,
        utilisateur_id: int,
        motif_annulation: str
    ) -> OrdreRemplacement:
        """
        Annule un ordre de remplacement.
        """
        ordre = self.get_ordre(ordre_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")
        
        if ordre.statut == StatutOrdreRemplacement.EXECUTE:
            raise ValueError("Impossible d'annuler un ordre déjà exécuté")
        
        ordre.statut = StatutOrdreRemplacement.ANNULE
        ordre.date_annulation = datetime.utcnow()
        ordre.annule_par_id = utilisateur_id
        ordre.motif_annulation = motif_annulation
        
        self.db.commit()
        self.db.refresh(ordre)
        
        # Journaliser l'annulation
        self.audit_service.log_action(
            user_id=utilisateur_id,
            table_name="ordres_remplacement",
            record_id=ordre_id,
            action="ANNULE",
            nouvelles_valeurs={
                "statut": ordre.statut.value,
                "motif_annulation": motif_annulation
            }
        )
        
        logger.info(f"Ordre {ordre_id} annulé par l'utilisateur {utilisateur_id}")
        return ordre

    def get_statistiques(self) -> Dict[str, Any]:
        """Retourne les statistiques des ordres de remplacement"""
        total = self.db.query(func.count(OrdreRemplacement.id)).scalar() or 0
        
        en_attente = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EN_ATTENTE
        ).scalar() or 0
        
        en_cours = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EN_COURS
        ).scalar() or 0
        
        valides = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.VALIDE
        ).scalar() or 0
        
        executes = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EXECUTE
        ).scalar() or 0
        
        rejetes = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.REJETE
        ).scalar() or 0
        
        annules = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.ANNULE
        ).scalar() or 0
        
        # Ordres en retard
        now = datetime.utcnow()
        en_retard = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS
            ]),
            OrdreRemplacement.date_echeance < now,
            OrdreRemplacement.date_echeance.isnot(None)
        ).scalar() or 0
        
        # Ordres par priorité
        par_priorite = {}
        for p in PrioriteOrdre:
            count = self.db.query(func.count(OrdreRemplacement.id)).filter(
                OrdreRemplacement.priorite == p.value
            ).scalar() or 0
            if count > 0:
                par_priorite[p.value] = count
        
        return {
            "total": total,
            "en_attente": en_attente,
            "en_cours": en_cours,
            "valides": valides,
            "executes": executes,
            "rejetes": rejetes,
            "annules": annules,
            "en_retard": en_retard,
            "par_priorite": par_priorite,
            "taux_execution": round((executes / total * 100), 1) if total > 0 else 0
        }

    def get_ordres_recents(self, limit: int = 10) -> List[OrdreRemplacement]:
        """Récupère les ordres récents"""
        return self.db.query(OrdreRemplacement).order_by(
            OrdreRemplacement.date_creation.desc()
        ).limit(limit).all()

    def get_ordres_par_periode(self, date_debut: datetime, date_fin: datetime) -> List[OrdreRemplacement]:
        """Récupère les ordres créés dans une période donnée"""
        return self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.date_creation >= date_debut,
            OrdreRemplacement.date_creation <= date_fin
        ).order_by(OrdreRemplacement.date_creation.desc()).all()

    def get_ordres_par_utilisateur(self, utilisateur_id: int) -> List[OrdreRemplacement]:
        """Récupère les ordres traités par un utilisateur"""
        return self.db.query(OrdreRemplacement).filter(
            or_(
                OrdreRemplacement.cree_par_id == utilisateur_id,
                OrdreRemplacement.valide_par_id == utilisateur_id,
                OrdreRemplacement.execute_par_id == utilisateur_id
            )
        ).order_by(OrdreRemplacement.date_creation.desc()).all()

    def verifier_et_relancer_ordres_en_retard(self) -> Dict[str, Any]:
        """
        Vérifie les ordres en retard et envoie des rappels.
        """
        ordres_retard = self.get_ordres_en_retard()
        resultats = {
            "total_en_retard": len(ordres_retard),
            "relances_envoyees": 0,
            "ordres_relances": []
        }
        
        for ordre in ordres_retard:
            bien = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
            designation = ordre.designation_bien or f"Bien #{ordre.bien_id}"
            
            # Envoyer une notification de rappel
            self.notification_service.envoyer_notification_par_role(
                role_nom="DG",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre=f"⚠️ RAPPEL - Ordre en retard : {designation}",
                contenu=f"L'ordre de remplacement pour le bien {designation} est en retard (échéance: {ordre.date_echeance.strftime('%d/%m/%Y') if ordre.date_echeance else 'Non définie'}). Veuillez prendre les mesures nécessaires.",
                lien=f"/ordres-remplacement/{ordre.id}"
            )
            
            resultats["relances_envoyees"] += 1
            resultats["ordres_relances"].append({
                "ordre_id": ordre.id,
                "bien_id": ordre.bien_id,
                "designation": designation,
                "date_echeance": ordre.date_echeance.isoformat() if ordre.date_echeance else None,
                "priorite": ordre.priorite
            })
            
            logger.info(f"Rappel envoyé pour l'ordre {ordre.id} en retard")
        
        return resultats

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Retourne les données pour le tableau de bord des ordres"""
        stats = self.get_statistiques()
        ordres_urgents = self.get_ordres_urgents()
        ordres_retard = self.get_ordres_en_retard()
        ordres_recents = self.get_ordres_recents(5)
        
        return {
            "statistiques": stats,
            "ordres_urgents": [
                {
                    "id": o.id,
                    "bien_id": o.bien_id,
                    "designation": o.designation_bien or f"Bien #{o.bien_id}",
                    "priorite": o.priorite,
                    "date_echeance": o.date_echeance.isoformat() if o.date_echeance else None,
                    "statut": o.statut.value
                }
                for o in ordres_urgents[:5]
            ],
            "ordres_retard": [
                {
                    "id": o.id,
                    "bien_id": o.bien_id,
                    "designation": o.designation_bien or f"Bien #{o.bien_id}",
                    "date_echeance": o.date_echeance.isoformat() if o.date_echeance else None,
                    "jours_retard": (datetime.utcnow() - o.date_echeance).days if o.date_echeance else 0
                }
                for o in ordres_retard[:5]
            ],
            "ordres_recents": [
                {
                    "id": o.id,
                    "bien_id": o.bien_id,
                    "designation": o.designation_bien or f"Bien #{o.bien_id}",
                    "statut": o.statut.value,
                    "date_creation": o.date_creation.isoformat() if o.date_creation else None
                }
                for o in ordres_recents
            ]
        }