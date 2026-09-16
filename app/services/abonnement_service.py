# backend/app/services/abonnement_service.py
# -*- coding: utf-8 -*-
"""
AbonnementService — Gestion des abonnements SaaS
Sprint 0 — Fondations OKAPI Flotte
"""
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import logging

from ..models.organisation import Organisation, PlanAbonnement, StatutOrganisation
from ..models.abonnement_facturation import (
    AbonnementFacturation,
    StatutPaiement,
)
from ..services.audit_service import AuditService
from ..services.notification_service import NotificationService
from ..services.organisation_service import QUOTAS_PAR_PLAN

logger = logging.getLogger(__name__)


class AbonnementService:
    """Service de gestion des abonnements SaaS (multi-ONG)."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)

    # ============================================================
    # 1. CRÉATION ET RENOUVELLEMENT
    # ============================================================

    def creer_abonnement(
        self,
        organisation_id: int,
        plan: str,
        duree_mois: int = 12,
        montant_mensuel: Optional[float] = None,
        user_id: Optional[int] = None,
    ) -> AbonnementFacturation:
        """
        Crée un abonnement pour une organisation.
        Génère la 1ère facture de la période en cours.
        """
        organisation = (
            self.db.query(Organisation)
            .filter(Organisation.id == organisation_id)
            .first()
        )
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        # Normaliser le plan
        try:
            plan_enum = PlanAbonnement[plan.upper()] if isinstance(plan, str) else plan
        except KeyError:
            raise ValueError(f"Plan invalide : {plan}")

        # Calculer les dates
        aujourd_hui = date.today()
        date_debut = organisation.date_debut or aujourd_hui
        date_fin = date_debut + timedelta(days=30 * duree_mois)

        # Mettre à jour l'organisation
        organisation.plan_abonnement = plan_enum
        quotas = QUOTAS_PAR_PLAN.get(plan_enum.value, QUOTAS_PAR_PLAN["BASIC"])
        organisation.quota_vehicules = quotas["quota_vehicules"]
        organisation.quota_chauffeurs = quotas["quota_chauffeurs"]
        organisation.quota_missions_mois = quotas["quota_missions_mois"]
        organisation.date_debut = date_debut
        organisation.date_fin = date_fin
        organisation.statut = StatutOrganisation.ACTIF
        organisation.date_modification = datetime.utcnow()

        # Créer la facture de la période
        periode = date_debut.strftime("%Y-%m")
        montant = montant_mensuel or self._montant_par_defaut(plan_enum)

        facture = AbonnementFacturation(
            organisation_id=organisation_id,
            periode=periode,
            montant=montant,
            devise=organisation.devise,
            statut_paiement=StatutPaiement.EN_ATTENTE,
            date_echeance=date_debut + timedelta(days=30),
        )
        self.db.add(facture)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="abonnements_facturation",
                    record_id=facture.id,
                    new_values={
                        "organisation_id": organisation_id,
                        "plan": plan_enum.value,
                        "periode": periode,
                        "montant": float(montant),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit création abonnement échoué : {e}")

        logger.info(
            f"Abonnement créé : {organisation.code} - Plan {plan_enum.value} "
            f"({date_debut} → {date_fin})"
        )
        return facture

    def renouveler_abonnement(
        self,
        organisation_id: int,
        duree_mois: int = 12,
        user_id: Optional[int] = None,
    ) -> AbonnementFacturation:
        """Renouvelle l'abonnement en créant la facture suivante."""
        organisation = (
            self.db.query(Organisation)
            .filter(Organisation.id == organisation_id)
            .first()
        )
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        aujourd_hui = date.today()
        date_debut = organisation.date_fin or aujourd_hui
        if date_debut < aujourd_hui:
            date_debut = aujourd_hui
        date_fin = date_debut + timedelta(days=30 * duree_mois)

        organisation.date_fin = date_fin
        organisation.statut = StatutOrganisation.ACTIF
        organisation.date_modification = datetime.utcnow()

        periode = date_debut.strftime("%Y-%m")
        montant = self._montant_par_defaut(organisation.plan_abonnement)

        facture = AbonnementFacturation(
            organisation_id=organisation_id,
            periode=periode,
            montant=montant,
            devise=organisation.devise,
            statut_paiement=StatutPaiement.EN_ATTENTE,
            date_echeance=date_debut + timedelta(days=30),
        )
        self.db.add(facture)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="abonnements_facturation",
                    record_id=facture.id,
                    action="RENOUVELLEMENT",
                    nouvelles_valeurs={
                        "organisation_id": organisation_id,
                        "periode": periode,
                        "montant": float(montant),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit renouvellement échoué : {e}")

        logger.info(f"Abonnement renouvelé : {organisation.code} jusqu'au {date_fin}")
        return facture

    # ============================================================
    # 2. VÉRIFICATION
    # ============================================================

    def verifier_abonnement_actif(self, organisation_id: int) -> Dict[str, Any]:
        """
        Vérifie qu'un abonnement est actif et non expiré.
        Retourne un dict avec est_actif, jours_restants, message.
        """
        organisation = (
            self.db.query(Organisation)
            .filter(Organisation.id == organisation_id)
            .first()
        )
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        # Vérifier le statut
        if organisation.statut != StatutOrganisation.ACTIF:
            return {
                "est_actif": False,
                "jours_restants": 0,
                "message": f"Organisation non active (statut: {organisation.statut.value})",
            }

        # Vérifier la date de fin
        if organisation.date_fin and organisation.date_fin < date.today():
            return {
                "est_actif": False,
                "jours_restants": 0,
                "message": f"Abonnement expiré depuis {organisation.date_fin}",
            }

        jours_restants = (
            (organisation.date_fin - date.today()).days
            if organisation.date_fin
            else 999999
        )

        return {
            "est_actif": True,
            "jours_restants": jours_restants,
            "date_fin": organisation.date_fin.isoformat() if organisation.date_fin else None,
            "message": (
                "Abonnement actif"
                if jours_restants > 30
                else f"Attention : expire dans {jours_restants} jours"
            ),
        }

    def calculer_quota(self, plan: str) -> Dict[str, int]:
        """Retourne les quotas associés à un plan."""
        try:
            plan_key = plan.upper() if isinstance(plan, str) else plan.value
        except AttributeError:
            raise ValueError(f"Plan invalide : {plan}")
        return QUOTAS_PAR_PLAN.get(plan_key, QUOTAS_PAR_PLAN["BASIC"])

    # ============================================================
    # 3. CRON — VÉRIFICATION ET NOTIFICATION
    # ============================================================

    def verifier_et_notifier_expirations(self, seuil_jours: int = 30) -> Dict[str, Any]:
        """
        Parcourt les organisations et :
        - Notifie celles dont l'abonnement expire dans < seuil_jours
        - Marque comme EXPIRE celles dont la date_fin est dépassée
        """
        aujourd_hui = date.today()
        organisations = self.db.query(Organisation).all()

        expirees = 0
        bientot = 0
        notifications_envoyees = 0

        for org in organisations:
            if not org.date_fin:
                continue

            jours_restants = (org.date_fin - aujourd_hui).days

            if jours_restants < 0 and org.statut == StatutOrganisation.ACTIF:
                org.statut = StatutOrganisation.EXPIRE
                org.date_modification = datetime.utcnow()
                expirees += 1

            elif 0 <= jours_restants <= seuil_jours:
                bientot += 1
                try:
                    # Notifier l'ADMIN de l'organisation
                    self.notification_service.envoyer_notification_par_role(
                        role_nom="ADMIN",
                        type_notif=self._type_notif_expiration(),
                        titre=f"⏰ Abonnement expire dans {jours_restants} jours",
                        contenu=(
                            f"L'abonnement de {org.nom} ({org.code}) expire le "
                            f"{org.date_fin}. Veuillez renouveler."
                        ),
                        lien="/admin/abonnement",
                    )
                    notifications_envoyees += 1
                except Exception as e:
                    logger.warning(f"Notification expiration échouée pour {org.code}: {e}")

        self.db.flush()

        logger.info(
            f"Vérification abonnements : {expirees} expirées, "
            f"{bientot} bientôt expirées, {notifications_envoyees} notifications"
        )

        return {
            "organisations_verifiees": len(organisations),
            "expirees": expirees,
            "bientot_expirees": bientot,
            "notifications_envoyees": notifications_envoyees,
        }

    # ============================================================
    # 4. UTILITAIRES
    # ============================================================

    def _montant_par_defaut(self, plan: PlanAbonnement) -> float:
        """Retourne le montant mensuel par défaut selon le plan."""
        tarifs = {
            PlanAbonnement.BASIC: 99.0,
            PlanAbonnement.PRO: 299.0,
            PlanAbonnement.ENTERPRISE: 0.0,  # Sur devis
        }
        return tarifs.get(plan, 99.0)

    def _type_notif_expiration(self):
        """Retourne le type de notification d'expiration (fallback)."""
        try:
            from ..models.notification import TypeNotificationEnum
            return TypeNotificationEnum.BESOIN_CREE
        except Exception:
            return None

    def lister_abonnements_organisation(
        self, organisation_id: int
    ) -> List[AbonnementFacturation]:
        """Liste tous les abonnements d'une organisation."""
        return (
            self.db.query(AbonnementFacturation)
            .filter(AbonnementFacturation.organisation_id == organisation_id)
            .order_by(AbonnementFacturation.date_creation.desc())
            .all()
        )