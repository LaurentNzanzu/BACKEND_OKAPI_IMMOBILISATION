# app/scripts/seed_permissions.py
"""
Script de seed des permissions et rôles du module Flotte.
À exécuter UNE FOIS après les migrations Sprint 0.

Usage :
    python -m app.scripts.seed_permissions
    ou
    python app/scripts/seed_permissions.py
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.permission import Permission
from app.models.role import Role  # adapter selon ton modèle existant
from app.models.permission import roles_permissions


PERMISSIONS_FLOTTE = [
    # Missions
    ("MISSION_CREATE",       "Créer une demande de mission",         "FLOTTE"),
    ("MISSION_VALIDATE_LOG", "Valider une mission (logistique)",     "FLOTTE"),
    ("MISSION_VALIDATE_DG",  "Valider une mission (direction)",      "FLOTTE"),
    ("MISSION_CLOSE",        "Clôturer une mission",                 "FLOTTE"),
    # Carburant
    ("CARBURANT_SAISIR",     "Saisir un ravitaillement",             "FLOTTE"),
    ("CARBURANT_VALIDER",    "Valider un ravitaillement",            "FLOTTE"),
    # Incidents
    ("INCIDENT_DECLARER",    "Déclarer un incident véhicule",        "FLOTTE"),
    ("INCIDENT_VALIDER",     "Valider un incident véhicule",         "FLOTTE"),
    # Chauffeurs & Projets
    ("CHAUFFEUR_GERER",      "Gérer les chauffeurs",                 "FLOTTE"),
    ("PROJET_GERER",         "Gérer les projets",                    "FLOTTE"),
    # Rapports & Alertes
    ("RAPPORT_FLOTTE_VOIR",  "Consulter les rapports flotte",        "FLOTTE"),
    ("RAPPORT_FLOTTE_EXPORTER", "Exporter les rapports flotte",      "FLOTTE"),
    ("ALERTE_TRAITER",       "Traiter/ignorer une alerte flotte",    "FLOTTE"),
]

NOUVEAUX_ROLES = [
    ("CHAUFFEUR",         "Chauffeur — accès mobile limité"),
    ("LOGISTICIEN",       "Responsable logistique — gestion missions"),
    ("RESPONSABLE_PROJET","Responsable projet — demandes + rapports"),
]


def seed_permissions(db: Session):
    """Insère les permissions flotte si elles n'existent pas."""
    for code, libelle, module in PERMISSIONS_FLOTTE:
        existing = db.query(Permission).filter(Permission.code == code).first()
        if not existing:
            db.add(Permission(code=code, libelle=libelle, module=module))
            print(f"  + Permission ajoutée : {code}")
        else:
            print(f"  = Permission déjà présente : {code}")


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