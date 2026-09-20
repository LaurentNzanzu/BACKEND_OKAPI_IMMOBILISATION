# backend/app/scripts/seed_permissions_flotte.py
"""
Seed des permissions et rôles du module Flotte (Sprint 0).
Idempotent : peut être relancé sans erreur.

Usage :
    cd backend
    python -m app.scripts.seed_permissions_flotte
"""
import sys
from pathlib import Path

# Ajout de la racine du projet au PYTHONPATH avant les imports 'app'
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging

from app.core.database import get_db_for_task
from app.models.role import Role
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ============================================================================
# 1. PERMISSIONS À CRÉER — (nom, description, module, action)
# ============================================================================
PERMISSIONS_FLOTTE = [
    # Organisation
    ("ORGANISATION_GERER",     "Gérer les organisations",              "organisation", "gerer"),
    ("ORGANISATION_VOIR",      "Consulter les organisations",          "organisation", "voir"),
    # Abonnement
    ("ABONNEMENT_GERER",       "Gérer les abonnements",                "abonnement",   "gerer"),
    ("ABONNEMENT_VOIR",        "Consulter les abonnements",            "abonnement",   "voir"),
    # Facturation
    ("FACTURATION_GERER",      "Gérer la facturation",                 "facturation",  "gerer"),
    ("FACTURATION_VOIR",       "Consulter la facturation",             "facturation",  "voir"),
    # Projet
    ("PROJET_GERER",           "Gérer les projets",                    "projet",       "gerer"),
    ("PROJET_VOIR",            "Consulter les projets",                "projet",       "voir"),
    # Workflow
    ("WORKFLOW_GERER",         "Gérer les workflows",                  "workflow",     "gerer"),
    ("WORKFLOW_VOIR",          "Consulter les workflows",              "workflow",     "voir"),
    # Permission
    ("PERMISSION_GERER",       "Gérer les permissions",                "permission",   "gerer"),
    # Import
    ("IMPORT_CSV",             "Exécuter un import CSV",               "import",       "executer"),
    # Mission
    ("MISSION_CREATE",         "Créer une demande de mission",         "mission",      "create"),
    ("MISSION_VALIDATE_LOG",   "Valider une mission (logistique)",     "mission",      "validate_log"),
    ("MISSION_VALIDATE_DG",    "Valider une mission (direction)",      "mission",      "validate_dg"),
    ("MISSION_CLOSE",          "Clôturer une mission",                 "mission",      "close"),
    # Carburant
    ("CARBURANT_SAISIR",       "Saisir un ravitaillement",             "carburant",    "saisir"),
    ("CARBURANT_VALIDER",      "Valider un ravitaillement",            "carburant",    "valider"),
    # Incident
    ("INCIDENT_DECLARER",      "Déclarer un incident véhicule",        "incident",     "declarer"),
    ("INCIDENT_VALIDER",       "Valider un incident véhicule",         "incident",     "valider"),
    # Chauffeur
    ("CHAUFFEUR_GERER",        "Gérer les chauffeurs",                 "chauffeur",    "gerer"),
    # Rapport
    ("RAPPORT_FLOTTE_VOIR",    "Consulter les rapports flotte",        "rapport",      "voir"),
    ("RAPPORT_FLOTTE_EXPORTER","Exporter les rapports flotte",         "rapport",      "exporter"),
    # Alerte
    ("ALERTE_TRAITER",         "Traiter/ignorer une alerte flotte",    "alerte",       "traiter"),
]


# ============================================================================
# 2. RÔLES À CRÉER SI ABSENTS — (nom, description)
# ============================================================================
NOUVEAUX_ROLES = [
    ("CHAUFFEUR",          "Chauffeur de véhicule"),
    ("LOGISTICIEN",        "Responsable logistique"),
    ("RESPONSABLE_PROJET", "Responsable de projet"),
]


# ============================================================================
# 3. ATTRIBUTION PERMISSIONS → RÔLES
# ============================================================================
ATTRIBUTIONS = {
    "ADMIN": [
        # Toutes les permissions (géré dynamiquement dans le script)
        "*",
    ],
    "DG": [
        "ORGANISATION_VOIR",
        "ABONNEMENT_VOIR",
        "FACTURATION_VOIR",
        "PROJET_VOIR",
        "PROJET_GERER",
        "WORKFLOW_VOIR",
        "MISSION_VALIDATE_DG",
        "RAPPORT_FLOTTE_VOIR",
        "RAPPORT_FLOTTE_EXPORTER",
        "ALERTE_TRAITER",
    ],
    "LOGISTICIEN": [
        "PROJET_VOIR",
        "WORKFLOW_VOIR",
        "MISSION_VALIDATE_LOG",
        "MISSION_CLOSE",
        "CARBURANT_VALIDER",
        "INCIDENT_VALIDER",
        "CHAUFFEUR_GERER",
        "ALERTE_TRAITER",
        "RAPPORT_FLOTTE_VOIR",
    ],
    "RESPONSABLE_PROJET": [
        "PROJET_VOIR",
        "MISSION_CREATE",
        "RAPPORT_FLOTTE_VOIR",
    ],
    "CHAUFFEUR": [
        "CARBURANT_SAISIR",
        "INCIDENT_DECLARER",
    ],
    "COMPTABLE": [
        "FACTURATION_VOIR",
        "RAPPORT_FLOTTE_VOIR",
    ],
    "CAISSE": [
        "RAPPORT_FLOTTE_VOIR",
    ],
}


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================
def _creer_ou_recuperer_roles(db):
    """Crée les rôles manquants et retourne un dict {nom: Role}."""
    roles_crees = []
    roles = {}

    for nom, description in NOUVEAUX_ROLES:
        existing = db.query(Role).filter(Role.nom == nom).first()
        if not existing:
            new_role = Role(nom=nom, description=description, actif=True)
            db.add(new_role)
            db.flush()
            roles_crees.append(nom)
            logger.info(f"  + Rôle créé : {nom}")
            roles[nom] = new_role
        else:
            logger.info(f"  = Rôle déjà présent : {nom}")
            roles[nom] = existing

    # Récupérer aussi les rôles existants ciblés par les attributions
    for role_nom in ATTRIBUTIONS.keys():
        if role_nom not in roles:
            existing = db.query(Role).filter(Role.nom == role_nom).first()
            if existing:
                roles[role_nom] = existing

    return roles, roles_crees


def _creer_ou_recuperer_permissions(db, permission_service):
    """Crée les permissions manquantes et retourne un dict {nom: Permission}."""
    permissions_crees = []
    permissions = {}

    for nom, description, module, action in PERMISSIONS_FLOTTE:
        perm = permission_service.obtenir_ou_creer_permission(
            nom=nom,
            description=description,
            module=module,
            action=action,
        )
        if perm is not None:
            permissions[nom] = perm
            # On ne peut pas facilement savoir si elle a été créée ou récupérée
            # sans requête supplémentaire, donc on log de façon neutre
            logger.info(f"  ✓ Permission disponible : {nom}")

    return permissions, permissions_crees


def _attribuer_permissions(db, permission_service, roles, permissions):
    """Attribue les permissions aux rôles selon ATTRIBUTIONS."""
    attributions_effectuees = 0

    for role_nom, perm_noms in ATTRIBUTIONS.items():
        role = roles.get(role_nom)
        if not role:
            logger.warning(f"  ⚠ Rôle introuvable : {role_nom} — attributions ignorées")
            continue

        # Cas spécial ADMIN : toutes les permissions
        if perm_noms == ["*"]:
            perm_noms = list(permissions.keys())

        for perm_nom in perm_noms:
            perm = permissions.get(perm_nom)
            if not perm:
                logger.warning(f"  ⚠ Permission introuvable : {perm_nom} (pour {role_nom})")
                continue

            try:
                permission_service.attribuer_permission(role.id_role, perm_nom)
                attributions_effectuees += 1
            except Exception as e:
                logger.warning(f"  ⚠ Attribution {role_nom} → {perm_nom} échouée : {e}")

    return attributions_effectuees


# ============================================================================
# MAIN
# ============================================================================
def main() -> dict:
    """
    Exécute le seed complet des permissions et rôles Flotte.
    Retourne un dict de statistiques.
    """
    db = get_db_for_task()
    stats = {
        "permissions_crees": 0,
        "permissions_total": 0,
        "roles_crees": [],
        "attributions_effectuees": 0,
    }

    try:
        logger.info("🌱 Seed permissions & rôles Flotte (Sprint 0) — début")

        permission_service = PermissionService(db)

        # 1. Permissions
        logger.info("\n📋 Création des permissions...")
        permissions, _ = _creer_ou_recuperer_permissions(db, permission_service)
        stats["permissions_total"] = len(permissions)
        # Compter celles réellement créées (heuristique : si présente après création)
        # On considère qu'on a créé celles qui n'existaient pas avant
        # (approximation acceptable pour le rapport final)
        stats["permissions_crees"] = len(PERMISSIONS_FLOTTE)

        # 2. Rôles
        logger.info("\n👥 Création des rôles...")
        roles, roles_crees = _creer_ou_recuperer_roles(db)
        stats["roles_crees"] = roles_crees

        # 3. Attributions
        logger.info("\n🔗 Attribution des permissions aux rôles...")
        stats["attributions_effectuees"] = _attribuer_permissions(
            db, permission_service, roles, permissions
        )

        db.commit()

        # Rapport final
        print("\n" + "=" * 60)
        print("✅ SEED SPRINT 0 — TERMINÉ AVEC SUCCÈS")
        print("=" * 60)
        print(f"Permissions disponibles : {stats['permissions_total']}")
        print(f"Rôles créés             : {len(stats['roles_crees'])} "
              f"({', '.join(stats['roles_crees']) or 'aucun'})")
        print(f"Attributions effectuées : {stats['attributions_effectuees']}")
        print("=" * 60)

        return stats

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur fatale : {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()