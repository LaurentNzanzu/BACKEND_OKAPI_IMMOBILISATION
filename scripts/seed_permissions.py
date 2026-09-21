# scripts/seed_permissions.py
# -*- coding: utf-8 -*-
"""
Script de seed complet des permissions et rôles.
Phase 5 — SaaS + Flotte multi-tenant OKAPI

Crée :
1. Toutes les permissions granulaires (SaaS + Flotte)
2. Tous les rôles métier
3. Toutes les associations rôles ↔ permissions

Idempotent : peut être relancé sans erreur.

Usage :
    python scripts/seed_permissions.py
    ou
    python -m scripts.seed_permissions
"""

import sys
from pathlib import Path

# ✅ Ajouter la racine au PYTHONPATH AVANT les imports 'app'
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.permission import Permission, role_permissions
from app.models.role import Role
from sqlalchemy import func


# ============================================================================
# 1. TOUTES LES PERMISSIONS (SaaS + Flotte)
# Format : (nom, description, module, action)
# ============================================================================

PERMISSIONS = [
    # ===================== SAAS — ORGANISATIONS =====================
    ("ORGANISATION_GERER",       "Gérer les organisations clientes",       "SAAS", "UPDATE"),
    ("ORGANISATION_VOIR",        "Consulter les organisations",            "SAAS", "READ"),

    # ===================== SAAS — ABONNEMENTS =====================
    ("ABONNEMENT_GERER",         "Gérer les abonnements",                  "SAAS", "UPDATE"),
    ("ABONNEMENT_VOIR",          "Consulter les abonnements",              "SAAS", "READ"),

    # ===================== SAAS — FACTURATION =====================
    ("FACTURATION_GERER",        "Gérer les factures",                     "SAAS", "UPDATE"),
    ("FACTURATION_VOIR",         "Consulter les factures",                 "SAAS", "READ"),

    # ===================== SAAS — PROJETS =====================
    ("PROJET_GERER",             "Gérer les projets bailleurs",            "SAAS", "UPDATE"),
    ("PROJET_VOIR",              "Consulter les projets bailleurs",        "SAAS", "READ"),

    # ===================== SAAS — WORKFLOW =====================
    ("WORKFLOW_GERER",           "Configurer les workflows",               "SAAS", "UPDATE"),
    ("WORKFLOW_VOIR",            "Consulter les workflows",                "SAAS", "READ"),

    # ===================== SAAS — PERMISSIONS =====================
    ("PERMISSION_GERER",         "Gérer les permissions des rôles",        "SAAS", "UPDATE"),

    # ===================== SAAS — IMPORT =====================
    ("IMPORT_CSV",               "Importer des données CSV",               "SAAS", "CREATE"),

    # ===================== FLOTTE — MISSIONS =====================
    ("MISSION_CREATE",           "Créer une demande de mission",           "FLOTTE", "CREATE"),
    ("MISSION_VALIDATE_LOG",     "Valider une mission (logistique)",       "FLOTTE", "VALIDATE"),
    ("MISSION_VALIDATE_DG",      "Valider une mission (direction)",        "FLOTTE", "VALIDATE"),
    ("MISSION_CLOSE",            "Clôturer une mission",                   "FLOTTE", "UPDATE"),

    # ===================== FLOTTE — CARBURANT =====================
    ("CARBURANT_SAISIR",         "Saisir un ravitaillement",               "FLOTTE", "CREATE"),
    ("CARBURANT_VALIDER",        "Valider un ravitaillement",              "FLOTTE", "VALIDATE"),

    # ===================== FLOTTE — INCIDENTS =====================
    ("INCIDENT_DECLARER",        "Déclarer un incident véhicule",          "FLOTTE", "CREATE"),
    ("INCIDENT_VALIDER",         "Valider un incident véhicule",           "FLOTTE", "VALIDATE"),

    # ===================== FLOTTE — CHAUFFEURS =====================
    ("CHAUFFEUR_GERER",          "Gérer les chauffeurs",                   "FLOTTE", "UPDATE"),

    # ===================== FLOTTE — RAPPORTS =====================
    ("RAPPORT_FLOTTE_VOIR",      "Consulter les rapports flotte",          "FLOTTE", "READ"),
    ("RAPPORT_FLOTTE_EXPORTER",  "Exporter les rapports flotte",           "FLOTTE", "READ"),

    # ===================== FLOTTE — ALERTES =====================
    ("ALERTE_TRAITER",           "Traiter/ignorer une alerte flotte",      "FLOTTE", "UPDATE"),
]


# ============================================================================
# 2. TOUS LES RÔLES
# Format : (nom, description)
# ============================================================================

ROLES = [
    # Rôles existants (déjà en base normalement)
    ("ADMIN",              "Administrateur — accès total"),
    ("DG",                 "Directeur Général"),
    ("COMPTABLE",          "Service comptable"),
    ("CAISSE",             "Service caisse"),
    ("TECHNICIEN",         "Technicien de maintenance"),
    ("MAGASINIER",         "Magasinier — gestion stock"),
    ("GESTIONNAIRE",       "Gestionnaire de biens"),

    # Nouveaux rôles Flotte
    ("CHAUFFEUR",          "Chauffeur — accès mobile limité"),
    ("LOGISTICIEN",        "Responsable logistique — gestion missions"),
    ("RESPONSABLE_PROJET", "Responsable projet — demandes + rapports"),
]


# ============================================================================
# 3. ASSOCIATIONS RÔLE ↔ PERMISSIONS
# Format : nom_role -> [liste des permissions]
# ============================================================================

ASSOCIATIONS = {
    # --------------------------------------------------------------------
    # ADMIN PLATEFORME : toutes les permissions (via bypass dans hasPermission)
    # MAIS on associe quand même explicitement pour la cohérence
    # --------------------------------------------------------------------
    "ADMIN": [
        "ORGANISATION_GERER", "ORGANISATION_VOIR",
        "ABONNEMENT_GERER", "ABONNEMENT_VOIR",
        "FACTURATION_GERER", "FACTURATION_VOIR",
        "PROJET_GERER", "PROJET_VOIR",
        "WORKFLOW_GERER", "WORKFLOW_VOIR",
        "PERMISSION_GERER",
        "IMPORT_CSV",
        "MISSION_CREATE", "MISSION_VALIDATE_LOG", "MISSION_VALIDATE_DG", "MISSION_CLOSE",
        "CARBURANT_SAISIR", "CARBURANT_VALIDER",
        "INCIDENT_DECLARER", "INCIDENT_VALIDER",
        "CHAUFFEUR_GERER",
        "RAPPORT_FLOTTE_VOIR", "RAPPORT_FLOTTE_EXPORTER",
        "ALERTE_TRAITER",
    ],

    # --------------------------------------------------------------------
    # DG : vision direction
    # --------------------------------------------------------------------
    "DG": [
        "ORGANISATION_VOIR",
        "ABONNEMENT_VOIR", "FACTURATION_VOIR",
        "PROJET_GERER", "PROJET_VOIR",
        "WORKFLOW_VOIR",
        "MISSION_VALIDATE_DG", "MISSION_CLOSE",
        "RAPPORT_FLOTTE_VOIR", "RAPPORT_FLOTTE_EXPORTER",
        "ALERTE_TRAITER",
    ],

    # --------------------------------------------------------------------
    # COMPTABLE
    # --------------------------------------------------------------------
    "COMPTABLE": [
        "FACTURATION_VOIR",
        "PROJET_VOIR",
        "RAPPORT_FLOTTE_VOIR",
    ],

    # --------------------------------------------------------------------
    # CAISSE
    # --------------------------------------------------------------------
    "CAISSE": [
        "RAPPORT_FLOTTE_VOIR",
    ],

    # --------------------------------------------------------------------
    # LOGISTICIEN : cœur métier Flotte
    # --------------------------------------------------------------------
    "LOGISTICIEN": [
        "PROJET_VOIR",
        "WORKFLOW_VOIR",
        "MISSION_CREATE", "MISSION_VALIDATE_LOG", "MISSION_CLOSE",
        "CARBURANT_VALIDER",
        "INCIDENT_VALIDER",
        "CHAUFFEUR_GERER",
        "RAPPORT_FLOTTE_VOIR",
        "ALERTE_TRAITER",
    ],

    # --------------------------------------------------------------------
    # RESPONSABLE_PROJET : création demandes + consultation rapports
    # --------------------------------------------------------------------
    "RESPONSABLE_PROJET": [
        "PROJET_VOIR",
        "WORKFLOW_VOIR",
        "MISSION_CREATE",
        "RAPPORT_FLOTTE_VOIR",
    ],

    # --------------------------------------------------------------------
    # CHAUFFEUR : accès mobile strict
    # --------------------------------------------------------------------
    "CHAUFFEUR": [
        "CARBURANT_SAISIR",
        "INCIDENT_DECLARER",
    ],
}


# ============================================================================
# FONCTIONS DE SEED
# ============================================================================

def seed_permissions(db: Session) -> dict:
    """Insère les permissions si absentes. Retourne {nom: Permission}."""
    print("\n🌱 [1/3] Seed des permissions...")
    created = 0
    existing = 0
    permissions_map = {}

    for nom, description, module, action in PERMISSIONS:
        perm = db.query(Permission).filter(Permission.nom == nom).first()
        if not perm:
            perm = Permission(
                nom=nom,
                description=description,
                module=module,
                action=action,
                actif=True,
            )
            db.add(perm)
            db.flush()
            created += 1
            print(f"  + Permission créée : {nom}")
        else:
            existing += 1
            print(f"  = Permission existante : {nom}")
        permissions_map[nom] = perm

    print(f"  → {created} créée(s), {existing} existante(s)")
    return permissions_map


def seed_roles(db: Session) -> dict:
    """Insère les rôles si absents. Retourne {nom: Role}."""
    print("\n🌱 [2/3] Seed des rôles...")
    created = 0
    existing = 0
    roles_map = {}

    for nom, description in ROLES:
        role = db.query(Role).filter(func.upper(Role.nom) == nom.upper()).first()
        if not role:
            role = Role(nom=nom, description=description, actif=True)
            db.add(role)
            db.flush()
            created += 1
            print(f"  + Rôle créé : {nom}")
        else:
            existing += 1
            print(f"  = Rôle existant : {nom}")
        roles_map[nom.upper()] = role

    print(f"  → {created} créé(s), {existing} existant(s)")
    return roles_map


def seed_associations(db: Session, permissions_map: dict, roles_map: dict) -> dict:
    """Associe les permissions aux rôles via role_permissions."""
    print("\n🌱 [3/3] Seed des associations rôle ↔ permissions...")
    stats = {"associations_creees": 0, "associations_existantes": 0, "manquants": []}

    for role_nom, perm_noms in ASSOCIATIONS.items():
        role = roles_map.get(role_nom.upper())
        if not role:
            stats["manquants"].append(f"Rôle '{role_nom}' introuvable")
            print(f"  ⚠️ Rôle '{role_nom}' introuvable → ignoré")
            continue

        for perm_nom in perm_noms:
            perm = permissions_map.get(perm_nom)
            if not perm:
                stats["manquants"].append(f"Permission '{perm_nom}' introuvable")
                print(f"  ⚠️ Permission '{perm_nom}' introuvable → ignorée")
                continue

            # Vérifier si l'association existe déjà
            exists = db.execute(
                role_permissions.select().where(
                    (role_permissions.c.id_role == role.id_role)
                    & (role_permissions.c.id_permission == perm.id_permission)
                )
            ).first()

            if exists:
                stats["associations_existantes"] += 1
            else:
                db.execute(
                    role_permissions.insert().values(
                        id_role=role.id_role,
                        id_permission=perm.id_permission,
                    )
                )
                stats["associations_creees"] += 1
                print(f"  + {role_nom} → {perm_nom}")

    print(
        f"  → {stats['associations_creees']} association(s) créée(s), "
        f"{stats['associations_existantes']} existante(s)"
    )
    return stats


# ============================================================================
# MAIN
# ============================================================================

def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("🌱 SEED PERMISSIONS & RÔLES — OKAPI Phase 5")
        print("=" * 70)

        permissions_map = seed_permissions(db)
        roles_map = seed_roles(db)
        stats = seed_associations(db, permissions_map, roles_map)

        db.commit()

        print("\n" + "=" * 70)
        print("✅ SEED TERMINÉ AVEC SUCCÈS")
        print("=" * 70)
        print(f"Permissions traitées : {len(permissions_map)}")
        print(f"Rôles traités        : {len(roles_map)}")
        print(f"Associations créées  : {stats['associations_creees']}")
        print(f"Associations exist.  : {stats['associations_existantes']}")

        if stats["manquants"]:
            print("\n⚠️ Éléments manquants :")
            for m in stats["manquants"]:
                print(f"  - {m}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()