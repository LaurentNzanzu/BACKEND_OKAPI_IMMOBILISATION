# backend/app/services/notification_trigger_service.py
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging

from ..models.notification import TypeNotificationEnum
from ..models.maintenance import Maintenance, StatutMaintenance
from ..models.amortissement import Amortissement, StatutAmortissement
from ..models.bien import Bien
from ..models.mouvement_bien import MouvementBien, TypeMouvementEnum
from ..models.piece_rechange import PieceRechange
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


class NotificationTriggerService:
    """Service déclencheur des notifications métier"""
    
    def __init__(self, db: Session):
        self.db = db
        self.notif_service = NotificationService(db)

    # ========== ALERTE MAINTENANCE (2 jours avant) ==========
    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def verifier_alertes_maintenance(self, organisation_id: Optional[int] = None):
        """Vérifie les maintenances planifiées dans 2 jours et envoie des alertes"""
        now = datetime.now(timezone.utc)
        target_date = now + timedelta(days=2)
        
        q_maint = self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee >= target_date.replace(hour=0, minute=0, second=0),
            Maintenance.date_planifiee < target_date.replace(hour=23, minute=59, second=59)
        )
        if organisation_id is not None:
            q_maint = q_maint.filter(Maintenance.organisation_id == organisation_id)
        maintenances = q_maint.all()
        
        notifications_envoyees = []
        for maintenance in maintenances:
            q_tech = self.db.query(Utilisateur).join(Role).filter(Role.nom == "TECHNICIEN")
            if organisation_id is not None:
                q_tech = q_tech.filter(Utilisateur.organisation_id == organisation_id)
            techniciens = q_tech.all()
            
            for technicien in techniciens:
                bien = maintenance.bien
                bien_nom = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
                
                notif = self.notif_service.envoyer_notification(
                    ids_destinataires=technicien.id,
                    type_notif=TypeNotificationEnum.ALERTE_FIN_ECHANCE_MAINTENANCE,
                    titre=f"🔧 Maintenance dans 2 jours - {bien_nom}",
                    contenu=f"La maintenance {maintenance.type_maintenance.value} prévue le {maintenance.date_planifiee.strftime('%d/%m/%Y')} approche. Veuillez vous préparer.",
                    lien=f"/maintenances/{maintenance.id_maintenance}"
                )
                notifications_envoyees.append(notif)
                logger.info(f"Notification maintenance envoyée à {technicien.email}")
        
        return notifications_envoyees
    # ═══ FIN MODIF 5.22 ═══

    # ========== ALERTE VNC ZERO ==========
    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def verifier_vnc_zero(self, organisation_id: Optional[int] = None):
        """Vérifie les biens dont la VNC a atteint 0 et alerte les comptables"""
        q_amort = self.db.query(Amortissement).filter(
            Amortissement.statut == StatutAmortissement.EN_COURS,
            Amortissement.valeur_nette_comptable <= 0
        )
        if organisation_id is not None:
            q_amort = q_amort.filter(Amortissement.organisation_id == organisation_id)
        amortissements = q_amort.all()
        
        notifications_envoyees = []
        for amort in amortissements:
            bien = amort.bien
            bien_nom = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
            
            q_comp = self.db.query(Utilisateur).join(Role).filter(Role.nom == "COMPTABLE")
            if organisation_id is not None:
                q_comp = q_comp.filter(Utilisateur.organisation_id == organisation_id)
            comptables = q_comp.all()
            
            for comptable in comptables:
                notif = self.notif_service.envoyer_notification(
                    ids_destinataires=comptable.id,
                    type_notif=TypeNotificationEnum.ALERTE_VNC_ZERO,
                    titre=f"📊 VNC à zéro - {bien_nom}",
                    contenu=f"Le bien '{bien_nom}' a atteint une valeur nette comptable de 0 USD. Il est totalement amorti.",
                    lien=f"/amortissements/fiche/{bien.id_bien}"
                )
                notifications_envoyees.append(notif)
                logger.info(f"Notification VNC zéro envoyée à {comptable.email}")
        
        return notifications_envoyees
    # ═══ FIN MODIF 5.22 ═══

    # ========== RAPPEL AMORTISSEMENT MANQUANT ==========
    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def verifier_amortissements_manquants(self, organisation_id: Optional[int] = None):
        """Vérifie les biens sans amortissement calculé pour l'exercice en cours"""
        exercice_courant = datetime.now().year
        
        q_biens = self.db.query(Bien).filter(
            ~Bien.amortissements.any(Amortissement.exercice == exercice_courant),
            Bien.date_acquisition < datetime(exercice_courant, 1, 1)
        )
        if organisation_id is not None:
            q_biens = q_biens.filter(Bien.organisation_id == organisation_id)
        biens_sans_amort = q_biens.all()
        
        notifications_envoyees = []
        if biens_sans_amort:
            q_comp = self.db.query(Utilisateur).join(Role).filter(Role.nom == "COMPTABLE")
            if organisation_id is not None:
                q_comp = q_comp.filter(Utilisateur.organisation_id == organisation_id)
            comptables = q_comp.all()
            
            for comptable in comptables:
                nb_biens = len(biens_sans_amort)
                notif = self.notif_service.envoyer_notification(
                    ids_destinataires=[comptable.id],
                    type_notif=TypeNotificationEnum.RAPPEL_AMORTISSEMENT_MANQUANT,
                    titre=f"⚠️ {nb_biens} bien(s) sans amortissement",
                    contenu=f"{nb_biens} bien(s) n'ont pas d'amortissement calculé pour l'exercice {exercice_courant}. Veuillez procéder au calcul.",
                    lien="/amortissements"
                )
                notifications_envoyees.append(notif)
                logger.info(f"Rappel amortissement envoyé à {comptable.email}")
        
        return notifications_envoyees
    # ═══ FIN MODIF 5.22 ═══

    # ========== NOTIFICATION MOUVEMENT ==========
    # ═══ MODIF 5.22 — Filtre ONG via le bien du mouvement ═══
    def notifier_mouvement(self, mouvement: MouvementBien):
        """Envoie une notification pour un mouvement de bien (cession/sortie)"""
        if mouvement.type_mouvement in [TypeMouvementEnum.CESSION, TypeMouvementEnum.SORTIE]:
            bien = mouvement.bien
            bien_nom = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
            org_id = getattr(bien, "organisation_id", None) if bien else None
            
            q_dg = self.db.query(Utilisateur).join(Role).filter(Role.nom == "DG")
            q_comp = self.db.query(Utilisateur).join(Role).filter(Role.nom == "COMPTABLE")
            if org_id is not None:
                q_dg = q_dg.filter(Utilisateur.organisation_id == org_id)
                q_comp = q_comp.filter(Utilisateur.organisation_id == org_id)
            dgs = q_dg.all()
            comptables = q_comp.all()
            destinataires = dgs + comptables
            
            for dest in destinataires:
                self.notif_service.envoyer_notification(
                    ids_destinataires=[dest.id],
                    type_notif=TypeNotificationEnum.MOUVEMENT_CREE,
                    titre=f"📦 Mouvement enregistré - {mouvement.type_mouvement.value}",
                    contenu=f"Le bien '{bien_nom}' a été {mouvement.type_mouvement.value.lower()} par {mouvement.responsable_sortie or 'inconnu'}. Motif: {mouvement.raison}",
                    lien=f"/mouvements/{mouvement.id_mouvement}"
                )
                logger.info(f"Notification mouvement envoyée à {dest.email}")
    # ═══ FIN MODIF 5.22 ═══

    # ========== NOTIFICATION AMORTISSEMENT CALCULE ==========
    # ═══ MODIF 5.22 — Filtre ONG via le bien de l'amortissement ═══
    def notifier_amortissement_calcule(self, amortissement: Amortissement):
        """Envoie une notification quand un amortissement est calculé"""
        bien = amortissement.bien
        bien_nom = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
        org_id = getattr(bien, "organisation_id", None) if bien else None
        
        q_comp = self.db.query(Utilisateur).join(Role).filter(Role.nom == "COMPTABLE")
        if org_id is not None:
            q_comp = q_comp.filter(Utilisateur.organisation_id == org_id)
        comptables = q_comp.all()
        
        for comptable in comptables:
            self.notif_service.envoyer_notification(
                ids_destinataires=comptable.id,
                type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                titre=f"📈 Amortissement calculé - {bien_nom}",
                contenu=f"L'amortissement du bien '{bien_nom}' a été calculé pour l'exercice {amortissement.exercice}. "
                        f"Dotation: {amortissement.annuite_comptable:,.0f} USD",
                lien=f"/amortissements/fiche/{bien.id_bien}"
            )
            logger.info(f"Notification amortissement envoyée à {comptable.email}")
    # ═══ FIN MODIF 5.22 ═══