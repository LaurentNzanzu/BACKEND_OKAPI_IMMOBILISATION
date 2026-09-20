# backend/app/services/organisation_service.py
# -*- coding: utf-8 -*-
"""
OrganisationService — Racine multi-tenant SaaS
Sprint 0 — Fondations OKAPI Flotte

Gère les ONG clientes, leurs quotas et leur cycle de vie.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import logging

from ..models.organisation import Organisation, PlanAbonnement, StatutOrganisation
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..services.audit_service import AuditService
from ..services.notification_service import NotificationService

logger = logging.getLogger(__name__)


# Quotas par plan (référentiel)
QUOTAS_PAR_PLAN: Dict[str, Dict[str, int]] = {
    "BASIC": {
        "quota_vehicules": 5,
        "quota_chauffeurs": 10,
        "quota_missions_mois": 50,
    },
    "PRO": {
        "quota_vehicules": 50,
        "quota_chauffeurs": 100,
        "quota_missions_mois": 500,
    },
    "ENTERPRISE": {
        "quota_vehicules": 999999,
        "quota_chauffeurs": 999999,
        "quota_missions_mois": 999999,
    },
}


class OrganisationService:
    """Service de gestion des organisations (multi-tenant SaaS)."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)

    # ============================================================
    # 1. CRUD ORGANISATION
    # ============================================================

    def creer_organisation(
        self, data: Dict[str, Any], user_id: Optional[int] = None
    ) -> Organisation:
        """
        Crée une nouvelle ONG cliente.
        - Applique les quotas du plan choisi automatiquement
        - Vérifie l'unicité du code
        - Crée un admin par défaut (optionnel : à faire dans un 2e temps)
        """
        code = (data.get("code") or "").strip().upper()
        if not code:
            raise ValueError("Le code de l'organisation est obligatoire")

        # Unicité du code
        existing = self.obtenir_par_code(code)
        if existing:
            raise ValueError(f"Une organisation avec le code '{code}' existe déjà")

        plan = data.get("plan_abonnement", PlanAbonnement.BASIC)
        if isinstance(plan, str):
            try:
                plan = PlanAbonnement[plan.upper()]
            except KeyError:
                raise ValueError(f"Plan d'abonnement invalide : {plan}")

        # Récupérer les quotas du plan
        quotas_plan = QUOTAS_PAR_PLAN.get(plan.value, QUOTAS_PAR_PLAN["BASIC"])

        organisation = Organisation(
            nom=data.get("nom"),
            code=code,
            email_admin=data.get("email_admin"),
            plan_abonnement=plan,
            quota_vehicules=data.get("quota_vehicules", quotas_plan["quota_vehicules"]),
            quota_chauffeurs=data.get("quota_chauffeurs", quotas_plan["quota_chauffeurs"]),
            quota_missions_mois=data.get("quota_missions_mois", quotas_plan["quota_missions_mois"]),
            devise=data.get("devise", "USD"),
            date_debut=data.get("date_debut"),
            date_fin=data.get("date_fin"),
            statut=StatutOrganisation.ACTIF,
            parametres_json=data.get("parametres_json", {}),
        )
        self.db.add(organisation)
        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="organisations",
                    record_id=organisation.id,
                    new_values={
                        "nom": organisation.nom,
                        "code": organisation.code,
                        "plan_abonnement": plan.value,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit création organisation échoué : {e}")

        logger.info(f"Organisation créée : {organisation.code} ({plan.value})")
        return organisation

    def obtenir_organisation(self, organisation_id: int) -> Optional[Organisation]:
        """Récupère une organisation par ID."""
        return (
            self.db.query(Organisation)
            .filter(Organisation.id == organisation_id)
            .first()
        )

    def obtenir_par_code(self, code: str) -> Optional[Organisation]:
        """Récupère une organisation par code."""
        if not code:
            return None
        return (
            self.db.query(Organisation)
            .filter(Organisation.code == code.strip().upper())
            .first()
        )

    def lister_organisations(
        self,
        statut: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Organisation]:
        """Liste les organisations avec filtres."""
        query = self.db.query(Organisation)

        if statut:
            try:
                statut_enum = StatutOrganisation[statut.upper()]
                query = query.filter(Organisation.statut == statut_enum)
            except KeyError:
                pass

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                (Organisation.nom.ilike(term))
                | (Organisation.code.ilike(term))
                | (Organisation.email_admin.ilike(term))
            )

        return (
            query.order_by(Organisation.date_creation.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def mettre_a_jour(
        self,
        organisation_id: int,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Organisation:
        """Met à jour une organisation."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        old_values = {
            "nom": organisation.nom,
            "email_admin": organisation.email_admin,
            "plan_abonnement": organisation.plan_abonnement.value if organisation.plan_abonnement else None,
            "quota_vehicules": organisation.quota_vehicules,
            "quota_chauffeurs": organisation.quota_chauffeurs,
            "quota_missions_mois": organisation.quota_missions_mois,
            "devise": organisation.devise,
        }

        # Champs modifiables (le code n'est PAS modifiable)
        champs_autorises = [
            "nom",
            "email_admin",
            "plan_abonnement",
            "quota_vehicules",
            "quota_chauffeurs",
            "quota_missions_mois",
            "devise",
            "date_debut",
            "date_fin",
            "parametres_json",
        ]

        for champ in champs_autorises:
            if champ in data and data[champ] is not None:
                setattr(organisation, champ, data[champ])

        organisation.date_modification = datetime.utcnow()
        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_update(
                    user_id=user_id,
                    table_name="organisations",
                    record_id=organisation.id,
                    old_values=old_values,
                    new_values={
                        "nom": organisation.nom,
                        "plan_abonnement": organisation.plan_abonnement.value if organisation.plan_abonnement else None,
                        "devise": organisation.devise,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit update organisation échoué : {e}")

        return organisation

    def suspendre(
        self, organisation_id: int, motif: str = None, user_id: Optional[int] = None
    ) -> Organisation:
        """Suspend une organisation (blocage d'accès)."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        if organisation.statut == StatutOrganisation.SUSPENDU:
            raise ValueError("Cette organisation est déjà suspendue")

        organisation.statut = StatutOrganisation.SUSPENDU
        organisation.date_modification = datetime.utcnow()
        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="organisations",
                    record_id=organisation.id,
                    action="SUSPENSION",
                    nouvelles_valeurs={"motif": motif, "statut": "SUSPENDU"},
                )
            except Exception as e:
                logger.warning(f"Audit suspension échoué : {e}")

        logger.warning(f"Organisation suspendue : {organisation.code} - Motif: {motif}")
        return organisation

    def reactiver(
        self, organisation_id: int, user_id: Optional[int] = None
    ) -> Organisation:
        """Réactive une organisation suspendue."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        if organisation.statut == StatutOrganisation.ACTIF:
            raise ValueError("Cette organisation est déjà active")

        organisation.statut = StatutOrganisation.ACTIF
        organisation.date_modification = datetime.utcnow()
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="organisations",
                    record_id=organisation.id,
                    action="REACTIVATION",
                    nouvelles_valeurs={"statut": "ACTIF"},
                )
            except Exception as e:
                logger.warning(f"Audit réactivation échoué : {e}")

        logger.info(f"Organisation réactivée : {organisation.code}")
        return organisation

    # ============================================================
    # 2. VÉRIFICATION DES QUOTAS
    # ============================================================

    def verifier_quota(
        self, organisation_id: int, type_ressource: str, marge: int = 0
    ) -> Dict[str, Any]:
        """
        Vérifie si l'organisation peut créer une nouvelle ressource.
        
        Args:
            organisation_id: ID de l'organisation
            type_ressource: "vehicules" | "chauffeurs" | "missions"
            marge: nombre supplémentaire à prévoir (par défaut 0)
        
        Returns:
            dict avec est_disponible, utilise, quota, message
        """
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        # Vérifier que l'abonnement est actif
        if organisation.statut != StatutOrganisation.ACTIF:
            return {
                "est_disponible": False,
                "utilise": 0,
                "quota": 0,
                "message": f"Organisation non active (statut: {organisation.statut.value})",
            }

        # Déterminer le quota et compter l'utilisation selon le type
        if type_ressource.lower() in ("vehicules", "vehicule"):
            quota = organisation.quota_vehicules
            utilise = self._compter_vehicules(organisation_id)
            label = "véhicules"

        elif type_ressource.lower() in ("chauffeurs", "chauffeur"):
            quota = organisation.quota_chauffeurs
            utilise = self._compter_chauffeurs(organisation_id)
            label = "chauffeurs"

        elif type_ressource.lower() in ("missions", "mission"):
            quota = organisation.quota_missions_mois
            utilise = self._compter_missions_du_mois(organisation_id)
            label = "missions ce mois"

        else:
            raise ValueError(f"Type de ressource inconnu : {type_ressource}")

        utilise_total = utilise + marge
        est_disponible = utilise_total < quota

        if est_disponible:
            message = f"Quota {label} disponible ({utilise_total}/{quota})"
        else:
            message = (
                f"Quota {label} atteint ({utilise_total}/{quota}). "
                f"Veuillez passer à un plan supérieur."
            )

        return {
            "est_disponible": est_disponible,
            "utilise": utilise,
            "quota": quota,
            "marge_demandee": marge,
            "message": message,
            "ressource": type_ressource,
        }

    def _compter_vehicules(self, organisation_id: int) -> int:
        """
        Compte les véhicules de l'organisation.
        Un véhicule = Bien avec id_type_bien correspondant au type VEHICULE.
        """
        try:
            from ..models.bien import Bien
            from ..models.type_bien import TypeBien

            type_vehicule = (
                self.db.query(TypeBien)
                .filter(TypeBien.code == "VEHICULE")
                .first()
            )
            if not type_vehicule:
                return 0

            return (
                self.db.query(func.count(Bien.id_bien))
                .filter(
                    Bien.organisation_id == organisation_id,
                    Bien.id_type_bien == type_vehicule.id,
                )
                .scalar()
                or 0
            )
        except Exception as e:
            logger.warning(f"Impossible de compter les véhicules : {e}")
            return 0

    def _compter_chauffeurs(self, organisation_id: int) -> int:
        """
        Compte les chauffeurs (Sprint 1).
        Retourne 0 si le modèle Chauffeur n'existe pas encore.
        """
        try:
            from ..models.chauffeur import Chauffeur
            return (
                self.db.query(func.count(Chauffeur.id))
                .filter(Chauffeur.organisation_id == organisation_id)
                .scalar()
                or 0
            )
        except ImportError:
            return 0
        except Exception as e:
            logger.warning(f"Impossible de compter les chauffeurs : {e}")
            return 0

    def _compter_missions_du_mois(self, organisation_id: int) -> int:
        """
        Compte les missions du mois en cours (Sprint 1).
        Retourne 0 si le modèle Mission n'existe pas encore.
        """
        try:
            from ..models.mission import Mission

            aujourd_hui = date.today()
            debut_mois = aujourd_hui.replace(day=1)

            return (
                self.db.query(func.count(Mission.id))
                .filter(
                    Mission.organisation_id == organisation_id,
                    Mission.date_creation >= debut_mois,
                )
                .scalar()
                or 0
            )
        except ImportError:
            return 0
        except Exception as e:
            logger.warning(f"Impossible de compter les missions : {e}")
            return 0

    # ============================================================
    # 3. UTILITAIRES
    # ============================================================

    def lister_utilisateurs_organisation(
        self, organisation_id: int, est_actif: Optional[bool] = None
    ) -> List[Utilisateur]:
        """Liste les utilisateurs d'une organisation."""
        query = self.db.query(Utilisateur).filter(
            Utilisateur.organisation_id == organisation_id
        )
        if est_actif is not None:
            query = query.filter(Utilisateur.est_actif == est_actif)
        return query.all()

    def get_quota_summary(self, organisation_id: int) -> Dict[str, Any]:
        """Retourne un résumé complet des quotas pour une organisation."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        return {
            "organisation_id": organisation.id,
            "code": organisation.code,
            "plan": organisation.plan_abonnement.value,
            "statut": organisation.statut.value,
            "vehicules": self.verifier_quota(organisation_id, "vehicules"),
            "chauffeurs": self.verifier_quota(organisation_id, "chauffeurs"),
            "missions_mois": self.verifier_quota(organisation_id, "missions"),
        }