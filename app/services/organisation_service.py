# backend/app/services/organisation_service.py
# -*- coding: utf-8 -*-
"""
OrganisationService — Racine multi-tenant SaaS
Phase 4 — Création auto de l'admin ONG + gestion modules activables
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date
import logging
import secrets
import string

from ..models.organisation import Organisation, PlanAbonnement, StatutOrganisation
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..services.audit_service import AuditService
from ..services.notification_service import NotificationService
from ..core.module_registry import (
    get_modules_pour_plan,
    normaliser_modules,
    lister_tous_modules,
)
from ..core.security import get_password_hash

logger = logging.getLogger(__name__)


# Quotas par plan (référentiel)
QUOTAS_PAR_PLAN: Dict[str, Dict[str, int]] = {
    "BASIC":      {"quota_vehicules": 5,      "quota_chauffeurs": 10,     "quota_missions_mois": 50},
    "PRO":        {"quota_vehicules": 50,     "quota_chauffeurs": 100,    "quota_missions_mois": 500},
    "ENTERPRISE": {"quota_vehicules": 999999, "quota_chauffeurs": 999999, "quota_missions_mois": 999999},
}


def _generer_mot_de_passe_temporaire(longueur: int = 12) -> str:
    """
    Génère un mot de passe temporaire FORT et SANS caractères ambigus.

    ✅ Exclut les caractères visuellement confondables :
    - Pas de O (lettre) — souvent confondu avec 0 (chiffre)
    - Pas de 0 (chiffre) — souvent confondu avec O (lettre)
    - Pas de l (L minuscule) — confondu avec 1 (un) ou I (i majuscule)
    - Pas de 1 (chiffre) — confondu avec l ou I
    - Pas de I (i majuscule) — confondu avec l ou 1
    - Pas de o (o minuscule) — confondu avec 0

    ✅ Garantit :
    - Au moins 1 majuscule
    - Au moins 1 minuscule
    - Au moins 1 chiffre
    - Au moins 1 symbole
    - Longueur totale = `longueur` (12 par défaut)

    ✅ Format du mot de passe résultant :
    - 12 caractères
    - Uniquement des caractères non ambigus
    - Difficile à deviner (secrets.SystemRandom)
    """
    # Alphabets SANS caractères ambigus
    MAJUSCULES = "ABCDEFGHJKLMNPQRSTUVWXYZ"       # sans I, O
    MINUSCULES = "abcdefghjkmnpqrstuvwxyz"        # sans l, o
    CHIFFRES   = "23456789"                        # sans 0, 1
    SYMBOLES   = "!@#$%&*"

    alphabet = MAJUSCULES + MINUSCULES + CHIFFRES

    # Garantir au moins 1 de chaque catégorie
    pwd_chars = [
        secrets.choice(MAJUSCULES),
        secrets.choice(MINUSCULES),
        secrets.choice(CHIFFRES),
        secrets.choice(SYMBOLES),
    ]

    # Compléter jusqu'à la longueur demandée
    pwd_chars += [secrets.choice(alphabet) for _ in range(max(0, longueur - 4))]

    # Mélanger de manière cryptographiquement sûre
    secrets.SystemRandom().shuffle(pwd_chars)

    return "".join(pwd_chars)

class OrganisationService:
    """Service de gestion des organisations (multi-tenant SaaS)."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)

    # ============================================================
    # 1. CRÉATION ORGANISATION + ADMIN AUTO
    # ============================================================

    def creer_organisation(
        self,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
        creer_admin: bool = True,
    ) -> Tuple[Organisation, Optional[Dict[str, str]]]:
        """
        Crée une nouvelle ONG cliente :
        - Applique les quotas du plan
        - Active les modules (selon plan ou liste fournie)
        - Crée l'utilisateur ADMIN de l'ONG (si creer_admin=True)
        - Génère un mot de passe temporaire

        Retourne : (organisation, credentials_admin)
        """
        code = (data.get("code") or "").strip().upper()
        if not code:
            raise ValueError("Le code de l'organisation est obligatoire")

        existing = self.obtenir_par_code(code)
        if existing:
            raise ValueError(f"Une organisation avec le code '{code}' existe déjà")

        plan = data.get("plan_abonnement", PlanAbonnement.BASIC)
        if isinstance(plan, str):
            try:
                plan = PlanAbonnement[plan.upper()]
            except KeyError:
                raise ValueError(f"Plan d'abonnement invalide : {plan}")

        quotas_plan = QUOTAS_PAR_PLAN.get(plan.value, QUOTAS_PAR_PLAN["BASIC"])

        # --- Modules actifs : liste fournie OU modules par défaut du plan
        modules_fournis = data.get("modules_actifs")
        if modules_fournis is None:
            modules_actifs = get_modules_pour_plan(plan.value)
        else:
            modules_actifs = normaliser_modules(modules_fournis)

        parametres_json = dict(data.get("parametres_json") or {})
        parametres_json["modules_actifs"] = modules_actifs

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
            parametres_json=parametres_json,
        )
        self.db.add(organisation)
        self.db.flush()

        # --- Création de l'admin ONG
        credentials_admin: Optional[Dict[str, str]] = None
        if creer_admin:
            credentials_admin = self._creer_admin_ong(
                organisation=organisation,
                email_admin=organisation.email_admin,
                user_id_creator=user_id,
            )

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
                        "modules_actifs": modules_actifs,
                        "admin_cree": creer_admin,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit création organisation échoué : {e}")

        logger.info(
            f"Organisation créée : {organisation.code} ({plan.value}) — "
            f"{len(modules_actifs)} module(s), admin={creer_admin}"
        )
        return organisation, credentials_admin

    def _creer_admin_ong(
        self,
        organisation: Organisation,
        email_admin: str,
        user_id_creator: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Crée le compte administrateur de l'ONG.
        Mot de passe temporaire + force le changement.
        """
        if not email_admin:
            raise ValueError("email_admin est obligatoire pour créer l'admin ONG")

        # Vérifier que l'email n'est pas déjà pris
        existing_user = (
            self.db.query(Utilisateur)
            .filter(Utilisateur.email == email_admin.strip().lower())
            .first()
        )
        if existing_user:
            raise ValueError(
                f"Un utilisateur avec l'email '{email_admin}' existe déjà "
                f"(utilisateur #{existing_user.id})"
            )

        # Récupérer le rôle ADMIN
        role_admin = self.db.query(Role).filter(func.upper(Role.nom) == "ADMIN").first()
        if not role_admin:
            raise ValueError("Rôle ADMIN introuvable en base. Exécutez le seed permissions.")

        mot_de_passe_temp = _generer_mot_de_passe_temporaire(12)

        # ✅ CORRECTION : Utiliser get_next_id() — pattern du codebase OKAPI
        # Empêche la collision avec utilisateurs_pkey quand la séquence
        # PostgreSQL est désynchronisée (ce qui arrive fréquemment quand
        # des IDs sont insérés manuellement en SQL).
        next_id = Utilisateur.get_next_id(self.db)

        admin = Utilisateur(
            id=next_id,                                       # ← AJOUT CRITIQUE
            email=email_admin.strip().lower(),
            nom=organisation.nom[:100],
            prenom="Admin",
            post_nom=None,
            telephone=None,
            mot_de_passe=get_password_hash(mot_de_passe_temp),
            est_actif=True,
            role_id=role_admin.id_role,
            organisation_id=organisation.id,
            doit_changer_mot_de_passe=True,
        )
        self.db.add(admin)
        self.db.flush()

        if user_id_creator:
            try:
                self.audit_service.log_create(
                    user_id=user_id_creator,
                    table_name="utilisateurs",
                    record_id=admin.id,
                    new_values={
                        "email": admin.email,
                        "organisation_id": organisation.id,
                        "role": "ADMIN",
                        "must_change_password": True,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit création admin ONG échoué : {e}")

        logger.info(f"Admin ONG créé : {admin.email} (org #{organisation.id})")
        return {
            "admin_email": admin.email,
            "admin_mot_de_passe_temporaire": mot_de_passe_temp,
            "admin_doit_changer_mdp": True,
        }

    # ============================================================
    # 2. GESTION DES MODULES
    # ============================================================

    def get_modules_actifs(self, organisation_id: int) -> List[str]:
        """Retourne la liste normalisée des modules actifs."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")
        return organisation.get_modules_actifs()

    def mettre_a_jour_modules(
        self,
        organisation_id: int,
        modules: List[str],
        user_id: Optional[int] = None,
    ) -> Organisation:
        """Active / désactive les modules d'une ONG (override)."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        old_modules = organisation.get_modules_actifs()
        organisation.set_modules_actifs(modules)
        organisation.date_modification = datetime.utcnow()
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_update(
                    user_id=user_id,
                    table_name="organisations",
                    record_id=organisation.id,
                    old_values={"modules_actifs": old_modules},
                    new_values={"modules_actifs": organisation.get_modules_actifs()},
                )
            except Exception as e:
                logger.warning(f"Audit mise à jour modules échoué : {e}")

        logger.info(
            f"Modules ONG #{organisation_id} mis à jour : "
            f"{len(old_modules)} → {len(organisation.get_modules_actifs())}"
        )
        return organisation

    def est_module_actif(self, organisation_id: int, module_code: str) -> bool:
        """Vérifie si un module est actif pour une ONG."""
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            return False
        return organisation.is_module_active(module_code)

    def lister_modules_disponibles(self) -> List[Dict[str, str]]:
        """Retourne la liste de tous les modules disponibles (référentiel)."""
        return lister_tous_modules()

    # ============================================================
    # 3. CRUD ORGANISATION
    # ============================================================

    def obtenir_organisation(self, organisation_id: int) -> Optional[Organisation]:
        return self.db.query(Organisation).filter(Organisation.id == organisation_id).first()

    def obtenir_par_code(self, code: str) -> Optional[Organisation]:
        if not code:
            return None
        return self.db.query(Organisation).filter(Organisation.code == code.strip().upper()).first()

    def lister_organisations(
        self,
        statut: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Organisation]:
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
        return query.order_by(Organisation.date_creation.desc()).offset(skip).limit(limit).all()

    def mettre_a_jour(
        self, organisation_id: int, data: Dict[str, Any], user_id: Optional[int] = None
    ) -> Organisation:
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

        # Champs modifiables
        champs_simples = [
            "nom", "email_admin", "plan_abonnement", "quota_vehicules",
            "quota_chauffeurs", "quota_missions_mois", "devise",
            "date_debut", "date_fin",
        ]
        for champ in champs_simples:
            if champ in data and data[champ] is not None:
                setattr(organisation, champ, data[champ])

        # Modules (traitement spécial)
        if "modules_actifs" in data and data["modules_actifs"] is not None:
            organisation.set_modules_actifs(data["modules_actifs"])

        organisation.date_modification = datetime.utcnow()
        self.db.flush()

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
                        "modules_actifs": organisation.get_modules_actifs(),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit update organisation échoué : {e}")
        return organisation

    def suspendre(
        self, organisation_id: int, motif: str = None, user_id: Optional[int] = None
    ) -> Organisation:
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")
        if organisation.statut == StatutOrganisation.SUSPENDU:
            raise ValueError("Cette organisation est déjà suspendue")
        organisation.statut = StatutOrganisation.SUSPENDU
        organisation.date_modification = datetime.utcnow()
        self.db.flush()
        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id, table_name="organisations", record_id=organisation.id,
                    action="SUSPENSION",
                    nouvelles_valeurs={"motif": motif, "statut": "SUSPENDU"},
                )
            except Exception as e:
                logger.warning(f"Audit suspension échoué : {e}")
        logger.warning(f"Organisation suspendue : {organisation.code} — Motif: {motif}")
        return organisation

    def reactiver(self, organisation_id: int, user_id: Optional[int] = None) -> Organisation:
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
                    user_id=user_id, table_name="organisations", record_id=organisation.id,
                    action="REACTIVATION",
                    nouvelles_valeurs={"statut": "ACTIF"},
                )
            except Exception as e:
                logger.warning(f"Audit réactivation échoué : {e}")
        return organisation

    # ============================================================
    # 4. QUOTAS (méthodes existantes conservées)
    # ============================================================

    def verifier_quota(
        self, organisation_id: int, type_ressource: str, marge: int = 0
    ) -> Dict[str, Any]:
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")
        if organisation.statut != StatutOrganisation.ACTIF:
            return {
                "est_disponible": False, "utilise": 0, "quota": 0,
                "message": f"Organisation non active (statut: {organisation.statut.value})",
            }

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
        message = (
            f"Quota {label} disponible ({utilise_total}/{quota})"
            if est_disponible
            else f"Quota {label} atteint ({utilise_total}/{quota}). Veuillez passer à un plan supérieur."
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
        try:
            from ..models.bien import Bien
            from ..models.type_bien import TypeBien
            type_vehicule = self.db.query(TypeBien).filter(TypeBien.code == "VEHICULE").first()
            if not type_vehicule:
                return 0
            return (
                self.db.query(func.count(Bien.id_bien))
                .filter(Bien.organisation_id == organisation_id, Bien.id_type_bien == type_vehicule.id)
                .scalar() or 0
            )
        except Exception as e:
            logger.warning(f"Impossible de compter les véhicules : {e}")
            return 0

    def _compter_chauffeurs(self, organisation_id: int) -> int:
        try:
            from ..models.chauffeur import Chauffeur
            return (
                self.db.query(func.count(Chauffeur.id))
                .filter(Chauffeur.organisation_id == organisation_id)
                .scalar() or 0
            )
        except ImportError:
            return 0
        except Exception as e:
            logger.warning(f"Impossible de compter les chauffeurs : {e}")
            return 0

    def _compter_missions_du_mois(self, organisation_id: int) -> int:
        try:
            from ..models.mission import Mission
            aujourd_hui = date.today()
            debut_mois = aujourd_hui.replace(day=1)
            return (
                self.db.query(func.count(Mission.id))
                .filter(Mission.organisation_id == organisation_id, Mission.date_creation >= debut_mois)
                .scalar() or 0
            )
        except ImportError:
            return 0
        except Exception as e:
            logger.warning(f"Impossible de compter les missions : {e}")
            return 0

    def lister_utilisateurs_organisation(
        self, organisation_id: int, est_actif: Optional[bool] = None
    ) -> List[Utilisateur]:
        query = self.db.query(Utilisateur).filter(Utilisateur.organisation_id == organisation_id)
        if est_actif is not None:
            query = query.filter(Utilisateur.est_actif == est_actif)
        return query.all()

    def get_quota_summary(self, organisation_id: int) -> Dict[str, Any]:
        organisation = self.obtenir_organisation(organisation_id)
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")
        return {
            "organisation_id": organisation.id,
            "code": organisation.code,
            "plan": organisation.plan_abonnement.value,
            "statut": organisation.statut.value,
            "modules_actifs": organisation.get_modules_actifs(),
            "vehicules": self.verifier_quota(organisation_id, "vehicules"),
            "chauffeurs": self.verifier_quota(organisation_id, "chauffeurs"),
            "missions_mois": self.verifier_quota(organisation_id, "missions"),
        }