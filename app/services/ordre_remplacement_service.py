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

    # ═══ 5.22 — Helpers multi-tenant ═══
    def _get_organisation_id_bien(self, bien_id: Optional[int]) -> Optional[int]:
        if not bien_id:
            return None
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        return getattr(bien, "organisation_id", None) if bien else None

    def _check_acces_ordre(self, ordre: OrdreRemplacement, organisation_id: Optional[int]) -> None:
        if organisation_id is None or not ordre:
            return
        org = getattr(ordre, "organisation_id", None)
        if org is None:
            org = self._get_organisation_id_bien(ordre.bien_id)
        if org is None:
            raise ValueError(
                f"Accès refusé : ordre #{ordre.id} sans organisation."
            )
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : ordre #{ordre.id} appartient à une autre organisation."
            )
    # ═══ FIN 5.22 ═══

    # ═══ MODIF 5.22 — Injection organisation_id ═══
    def creer_ordre(
        self,
        bien_id: int,
        motif: str,
        alerte_id: Optional[int] = None,
        priorite: Optional[str] = None,
        utilisateur_id: Optional[int] = None,
        organisation_id: Optional[int] = None,
    ) -> OrdreRemplacement:
        """Crée un ordre de remplacement pour le DG et le Comptable."""
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        # ═══ 5.22 — Résolution org_id ═══
        org_id = organisation_id if organisation_id is not None else getattr(bien, "organisation_id", None)
        # ═══ FIN 5.22 ═══

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
        
        if not priorite:
            if bien.est_critique:
                priorite = PrioriteOrdre.CRITIQUE.value
            else:
                priorite = PrioriteOrdre.NORMALE.value
        
        designation = self._get_bien_designation(bien)
        prix_acquisition = float(bien.prix_acquisition or 0)
        vnc = bien.valeur_nette_comptable
        
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
            cree_par_id=utilisateur_id,
            organisation_id=org_id,   # ═══ 5.22 ═══
        )
        
        self.db.add(ordre)
        self.db.commit()
        self.db.refresh(ordre)
        
        if alerte_id:
            alerte = self.db.query(AlerteVNC).filter(AlerteVNC.id == alerte_id).first()
            if alerte:
                alerte.statut = StatutAlerteVNC.EN_COURS
                self.db.commit()
        
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
        
        self._notifier_creation_ordre(ordre)
        
        logger.info(f"Ordre de remplacement créé pour le bien {bien_id} - Motif: {motif}")
        return ordre
    # ═══ FIN MODIF 5.22 ═══

    def _calculer_date_echeance(self, priorite: str, est_critique: bool) -> datetime:
        now = datetime.utcnow()
        if priorite == PrioriteOrdre.CRITIQUE.value:
            return now + timedelta(days=7)
        elif priorite == PrioriteOrdre.URGENT.value:
            return now + timedelta(days=15)
        elif priorite == PrioriteOrdre.NORMALE.value:
            return now + timedelta(days=30)
        else:
            return now + timedelta(days=45)

    def _get_bien_designation(self, bien: Bien) -> str:
        if hasattr(bien, 'marque') and bien.marque:
            designation = f"{bien.marque} {getattr(bien, 'modele', '')}".strip()
            return designation or f"Bien #{bien.id_bien}"
        elif hasattr(bien, 'fabricant') and bien.fabricant:
            designation = f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip()
            return designation or f"Bien #{bien.id_bien}"
        return bien.description or f"Bien #{bien.id_bien}"

    def _notifier_creation_ordre(self, ordre: OrdreRemplacement):
        """Notifie les responsables de la création d'un ordre."""
        bien = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
        designation = ordre.designation_bien or f"Bien #{ordre.bien_id}"
        organisation_id = getattr(ordre, "organisation_id", None) or (getattr(bien, "organisation_id", None) if bien else None)

        if ordre.priorite == PrioriteOrdre.CRITIQUE.value:
            titre = f"🚨 ORDRE CRITIQUE - Remplacement requis : {designation}"
            contenu = f"Le bien {designation} a atteint son seuil de sécurité VNC. Remplacement URGENT requis. VNC: {ordre.vnc_actuelle:.2f} USD"
        elif ordre.priorite == PrioriteOrdre.URGENT.value:
            titre = f"⚠️ ORDRE URGENT - Remplacement requis : {designation}"
            contenu = f"Le bien {designation} nécessite un remplacement rapide. VNC: {ordre.vnc_actuelle:.2f} USD"
        else:
            titre = f"📋 Ordre de remplacement - {designation}"
            contenu = f"Le bien {designation} doit être remplacé. VNC: {ordre.vnc_actuelle:.2f} USD"
        
        contenu += f"\nMotif: {ordre.motif}"
        contenu += f"\nÉchéance: {ordre.date_echeance.strftime('%d/%m/%Y') if ordre.date_echeance else 'Non définie'}"
        
        self.notification_service.envoyer_notification_par_role_avec_ong(
            role_nom="DG",
            organisation_id=organisation_id,
            type_notif=TypeNotificationEnum.ALERTE_VNC_ZERO,
            titre=titre,
            contenu=contenu,
            lien=f"/ordres-remplacement/{ordre.id}"
        )
        
        self.notification_service.envoyer_notification_par_role_avec_ong(
            role_nom="COMPTABLE",
            organisation_id=organisation_id,
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"💰 {titre}",
            contenu=contenu,
            lien=f"/ordres-remplacement/{ordre.id}"
        )
        
        self.notification_service.envoyer_notification_par_role_avec_ong(
            role_nom="ADMIN",
            organisation_id=organisation_id,
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"📋 {titre}",
            contenu=f"Un ordre de remplacement a été créé pour le bien {designation}. Veuillez suivre le traitement.",
            lien=f"/ordres-remplacement/{ordre.id}"
        )

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_ordre(self, ordre_id: int, organisation_id: Optional[int] = None) -> Optional[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement).filter(OrdreRemplacement.id == ordre_id)
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.first()

    def get_ordres_par_bien(self, bien_id: int, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        self._check_acces_ordre_bien(bien_id, organisation_id)
        query = self.db.query(OrdreRemplacement).filter(OrdreRemplacement.bien_id == bien_id)
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_creation.desc()).all()

    def _check_acces_ordre_bien(self, bien_id: int, organisation_id: Optional[int]) -> None:
        if organisation_id is None:
            return
        org = self._get_organisation_id_bien(bien_id)
        if org is None:
            raise ValueError(f"Accès refusé : bien #{bien_id} sans organisation.")
        if org != organisation_id:
            raise ValueError(f"Accès refusé : bien #{bien_id} appartient à une autre organisation.")

    def get_ordres_en_attente(self, limit: int = 50, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EN_ATTENTE
        )
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_echeance.asc()).limit(limit).all()

    def get_ordres_en_cours(self, limit: int = 50, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut == StatutOrdreRemplacement.EN_COURS
        )
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_creation.desc()).limit(limit).all()

    def get_ordres_urgents(self, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS
            ]),
            OrdreRemplacement.priorite.in_([
                PrioriteOrdre.CRITIQUE.value,
                PrioriteOrdre.URGENT.value
            ])
        )
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_echeance.asc()).all()

    def get_ordres_en_retard(self, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        now = datetime.utcnow()
        query = self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS
            ]),
            OrdreRemplacement.date_echeance < now,
            OrdreRemplacement.date_echeance.isnot(None)
        )
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_echeance.asc()).all()

    def valider_ordre(self, ordre_id: int, utilisateur_id: int, bien_remplacement_id: Optional[int] = None, observations: Optional[str] = None, organisation_id: Optional[int] = None) -> OrdreRemplacement:
        ordre = self.get_ordre(ordre_id, organisation_id=organisation_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")

        self._check_acces_ordre(ordre, organisation_id)

        if ordre.statut != StatutOrdreRemplacement.EN_ATTENTE:
            raise ValueError(f"Impossible de valider un ordre en statut {ordre.statut.value}")
        
        utilisateur = self.db.query(Utilisateur).filter(Utilisateur.id == utilisateur_id).first()
        if not utilisateur:
            raise ValueError(f"Utilisateur {utilisateur_id} non trouvé")
        
        roles = [r.nom for r in utilisateur.roles]
        if not any(r in ["DG", "COMPTABLE", "ADMIN"] for r in roles):
            raise ValueError("Seul le DG, le Comptable ou l'Admin peut valider un ordre")
        
        ordre.statut = StatutOrdreRemplacement.VALIDE
        ordre.date_validation = datetime.utcnow()
        ordre.valide_par_id = utilisateur_id
        ordre.bien_remplacement_id = bien_remplacement_id
        ordre.observations = observations
        
        self.db.commit()
        self.db.refresh(ordre)
        
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
        
        bien = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
        designation = ordre.designation_bien or f"Bien #{ordre.bien_id}"
        org_id = getattr(ordre, "organisation_id", None) or (getattr(bien, "organisation_id", None) if bien else None)
        
        self.notification_service.envoyer_notification_par_role_avec_ong(
            role_nom="DG",
            organisation_id=org_id,
            type_notif=TypeNotificationEnum.BESOIN_VALIDE,
            titre=f"✅ Ordre validé - {designation}",
            contenu=f"L'ordre de remplacement pour le bien {designation} a été validé par {utilisateur.nom}.",
            lien=f"/ordres-remplacement/{ordre.id}"
        )
        
        logger.info(f"Ordre {ordre_id} validé par l'utilisateur {utilisateur_id}")
        return ordre

    def executer_ordre(self, ordre_id: int, utilisateur_id: int, bien_remplacement_id: int, observations: Optional[str] = None, organisation_id: Optional[int] = None) -> OrdreRemplacement:
        ordre = self.get_ordre(ordre_id, organisation_id=organisation_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")

        self._check_acces_ordre(ordre, organisation_id)

        if ordre.statut not in [StatutOrdreRemplacement.EN_ATTENTE, StatutOrdreRemplacement.VALIDE]:
            raise ValueError(f"Impossible d'exécuter un ordre en statut {ordre.statut.value}")
        
        bien_remplacement = self.db.query(Bien).filter(Bien.id_bien == bien_remplacement_id).first()
        if not bien_remplacement:
            raise ValueError(f"Bien de remplacement {bien_remplacement_id} non trouvé")
        
        ordre.statut = StatutOrdreRemplacement.EXECUTE
        ordre.date_execution = datetime.utcnow()
        ordre.execute_par_id = utilisateur_id
        ordre.bien_remplacement_id = bien_remplacement_id
        if observations:
            ordre.observations = (ordre.observations or "") + f"\nExécution: {observations}"
        
        bien_original = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
        if bien_original:
            bien_original.statut_comptable = "CEDE"
            bien_original.date_sortie = datetime.utcnow()
            bien_original.actif_remplacement_id = bien_remplacement_id
            self.db.commit()
        
        self.db.commit()
        self.db.refresh(ordre)
        
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
        
        self.notification_service.envoyer_alerte_remplacement(
            bien_id=ordre.bien_id,
            bien_nouveau_id=bien_remplacement_id
        )
        
        logger.info(f"Ordre {ordre_id} exécuté avec le bien de remplacement {bien_remplacement_id}")
        return ordre

    def rejeter_ordre(self, ordre_id: int, utilisateur_id: int, motif_rejet: str, organisation_id: Optional[int] = None) -> OrdreRemplacement:
        ordre = self.get_ordre(ordre_id, organisation_id=organisation_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")

        self._check_acces_ordre(ordre, organisation_id)

        if ordre.statut != StatutOrdreRemplacement.EN_ATTENTE:
            raise ValueError(f"Impossible de rejeter un ordre en statut {ordre.statut.value}")
        
        ordre.statut = StatutOrdreRemplacement.REJETE
        ordre.date_rejet = datetime.utcnow()
        ordre.rejete_par_id = utilisateur_id
        ordre.motif_rejet = motif_rejet
        
        self.db.commit()
        self.db.refresh(ordre)
        
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

    def annuler_ordre(self, ordre_id: int, utilisateur_id: int, motif_annulation: str, organisation_id: Optional[int] = None) -> OrdreRemplacement:
        ordre = self.get_ordre(ordre_id, organisation_id=organisation_id)
        if not ordre:
            raise ValueError(f"Ordre {ordre_id} non trouvé")

        self._check_acces_ordre(ordre, organisation_id)

        if ordre.statut == StatutOrdreRemplacement.EXECUTE:
            raise ValueError("Impossible d'annuler un ordre déjà exécuté")
        
        ordre.statut = StatutOrdreRemplacement.ANNULE
        ordre.date_annulation = datetime.utcnow()
        ordre.annule_par_id = utilisateur_id
        ordre.motif_annulation = motif_annulation
        
        self.db.commit()
        self.db.refresh(ordre)
        
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

    def get_statistiques(self, organisation_id: Optional[int] = None) -> Dict[str, Any]:
        base = self.db.query(OrdreRemplacement)
        if organisation_id is not None:
            base = base.filter(OrdreRemplacement.organisation_id == organisation_id)
        total = base.count()

        def count_status(statut):
            q = self.db.query(func.count(OrdreRemplacement.id)).filter(OrdreRemplacement.statut == statut)
            if organisation_id is not None:
                q = q.filter(OrdreRemplacement.organisation_id == organisation_id)
            return q.scalar() or 0

        en_attente = count_status(StatutOrdreRemplacement.EN_ATTENTE)
        en_cours = count_status(StatutOrdreRemplacement.EN_COURS)
        valides = count_status(StatutOrdreRemplacement.VALIDE)
        executes = count_status(StatutOrdreRemplacement.EXECUTE)
        rejetes = count_status(StatutOrdreRemplacement.REJETE)
        annules = count_status(StatutOrdreRemplacement.ANNULE)
        
        now = datetime.utcnow()
        q_retard = self.db.query(func.count(OrdreRemplacement.id)).filter(
            OrdreRemplacement.statut.in_([
                StatutOrdreRemplacement.EN_ATTENTE,
                StatutOrdreRemplacement.EN_COURS
            ]),
            OrdreRemplacement.date_echeance < now,
            OrdreRemplacement.date_echeance.isnot(None)
        )
        if organisation_id is not None:
            q_retard = q_retard.filter(OrdreRemplacement.organisation_id == organisation_id)
        en_retard = q_retard.scalar() or 0
        
        par_priorite = {}
        for p in PrioriteOrdre:
            q = self.db.query(func.count(OrdreRemplacement.id)).filter(OrdreRemplacement.priorite == p.value)
            if organisation_id is not None:
                q = q.filter(OrdreRemplacement.organisation_id == organisation_id)
            count = q.scalar() or 0
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

    def get_ordres_recents(self, limit: int = 10, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement)
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_creation.desc()).limit(limit).all()

    def get_ordres_par_periode(self, date_debut: datetime, date_fin: datetime, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement).filter(
            OrdreRemplacement.date_creation >= date_debut,
            OrdreRemplacement.date_creation <= date_fin
        )
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_creation.desc()).all()

    def get_ordres_par_utilisateur(self, utilisateur_id: int, organisation_id: Optional[int] = None) -> List[OrdreRemplacement]:
        query = self.db.query(OrdreRemplacement).filter(
            or_(
                OrdreRemplacement.cree_par_id == utilisateur_id,
                OrdreRemplacement.valide_par_id == utilisateur_id,
                OrdreRemplacement.execute_par_id == utilisateur_id
            )
        )
        if organisation_id is not None:
            query = query.filter(OrdreRemplacement.organisation_id == organisation_id)
        return query.order_by(OrdreRemplacement.date_creation.desc()).all()

    def verifier_et_relancer_ordres_en_retard(self, organisation_id: Optional[int] = None) -> Dict[str, Any]:
        ordres_retard = self.get_ordres_en_retard(organisation_id=organisation_id)
        resultats = {
            "total_en_retard": len(ordres_retard),
            "relances_envoyees": 0,
            "ordres_relances": []
        }
        
        for ordre in ordres_retard:
            bien = self.db.query(Bien).filter(Bien.id_bien == ordre.bien_id).first()
            designation = ordre.designation_bien or f"Bien #{ordre.bien_id}"
            org_id = getattr(ordre, "organisation_id", None) or (getattr(bien, "organisation_id", None) if bien else None)
            
            self.notification_service.envoyer_notification_par_role_avec_ong(
                role_nom="DG",
                organisation_id=org_id,
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

    def get_dashboard_data(self, organisation_id: Optional[int] = None) -> Dict[str, Any]:
        stats = self.get_statistiques(organisation_id=organisation_id)
        ordres_urgents = self.get_ordres_urgents(organisation_id=organisation_id)
        ordres_retard = self.get_ordres_en_retard(organisation_id=organisation_id)
        ordres_recents = self.get_ordres_recents(5, organisation_id=organisation_id)
        
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
    # ═══ FIN MODIF 5.22 ═══