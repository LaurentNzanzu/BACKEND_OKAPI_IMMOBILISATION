# scripts/seed_permissions.py
"""
Script de seed des permissions et rôles du module Flotte.
À exécuter UNE FOIS après les migrations Sprint 0.

Usage :
    python scripts/seed_permissions.py
    ou
    python -m scripts.seed_permissions
"""

import sys
from pathlib import Path

# ✅ IMPORTANT : Ajouter la racine du projet au PYTHONPATH AVANT les imports 'app'
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ✅ Imports corrigés
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.permission import Permission
from app.models.role import Role


# ============================================================================
# Structure : (nom, description, module, action)
# - nom         : identifiant unique de la permission (ex: "MISSION_CREATE")
# - description : libellé lisible
# - module      : domaine fonctionnel (ex: "FLOTTE")
# - action      : action CRUD (CREATE, READ, UPDATE, DELETE, VALIDATE, ...)
# ============================================================================
PERMISSIONS_FLOTTE = [
    # Missions
    ("MISSION_CREATE",          "Créer une demande de mission",         "FLOTTE", "CREATE"),
    ("MISSION_VALIDATE_LOG",    "Valider une mission (logistique)",     "FLOTTE", "VALIDATE"),
    ("MISSION_VALIDATE_DG",     "Valider une mission (direction)",      "FLOTTE", "VALIDATE"),
    ("MISSION_CLOSE",           "Clôturer une mission",                 "FLOTTE", "UPDATE"),
    # Carburant
    ("CARBURANT_SAISIR",        "Saisir un ravitaillement",             "FLOTTE", "CREATE"),
    ("CARBURANT_VALIDER",       "Valider un ravitaillement",            "FLOTTE", "VALIDATE"),
    # Incidents
    ("INCIDENT_DECLARER",       "Déclarer un incident véhicule",        "FLOTTE", "CREATE"),
    ("INCIDENT_VALIDER",        "Valider un incident véhicule",         "FLOTTE", "VALIDATE"),
    # Chauffeurs & Projets
    ("CHAUFFEUR_GERER",         "Gérer les chauffeurs",                 "FLOTTE", "UPDATE"),
    ("PROJET_GERER",            "Gérer les projets",                    "FLOTTE", "UPDATE"),
    # Rapports & Alertes
    ("RAPPORT_FLOTTE_VOIR",     "Consulter les rapports flotte",        "FLOTTE", "READ"),
    ("RAPPORT_FLOTTE_EXPORTER", "Exporter les rapports flotte",         "FLOTTE", "READ"),
    ("ALERTE_TRAITER",          "Traiter/ignorer une alerte flotte",    "FLOTTE", "UPDATE"),
]

NOUVEAUX_ROLES = [
    ("CHAUFFEUR",         "Chauffeur — accès mobile limité"),
    ("LOGISTICIEN",       "Responsable logistique — gestion missions"),
    ("RESPONSABLE_PROJET","Responsable projet — demandes + rapports"),
]


def seed_permissions(db: Session):
    """Insère les permissions flotte si elles n'existent pas."""
    for nom, description, module, action in PERMISSIONS_FLOTTE:
        existing = db.query(Permission).filter(Permission.nom == nom).first()
        if not existing:
            db.add(Permission(
                nom=nom,
                description=description,
                module=module,
                action=action,
                actif=True,
            ))
            print(f"  + Permission ajoutée : {nom}")
        else:
            print(f"  = Permission déjà présente : {nom}")


def seed_roles(db: Session):
    """Insère les nouveaux rôles si absents."""
    for nom, description in NOUVEAUX_ROLES:
        existing = db.query(Role).filter(Role.nom == nom).first()
        if not existing:
            db.add(Role(nom=nom, description=description))
            print(f"  + Rôle ajouté : {nom}")
        else:
            print(f"  = Rôle déjà présent : {nom}")


def main():
    db = SessionLocal()
    try:
        print("🌱 Seed des permissions flotte...")
        seed_permissions(db)
        print("\n🌱 Seed des rôles flotte...")
        seed_roles(db)
        db.commit()
        print("\n✅ Seed terminé avec succès.")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Erreur : {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()