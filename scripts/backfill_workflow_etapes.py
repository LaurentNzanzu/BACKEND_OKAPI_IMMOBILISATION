# scripts/backfill_workflow_etapes.py
# -*- coding: utf-8 -*-
"""
Script de rattrapage (backfill) pour initialiser les étapes de workflow par défaut
pour toutes les organisations existantes dans la base de données.
Idempotent : ignore les étapes déjà existantes.
"""
import sys
import os

# Ajouter le répertoire racine du backend au sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.models.organisation import Organisation
from app.models.workflow_etape import WorkflowEtape
from app.services.workflow_service import WorkflowService


def main():
    db = SessionLocal()
    try:
        organisations = db.query(Organisation).all()
        print(f"Trouvé {len(organisations)} organisation(s) à traiter.")

        workflow_service = WorkflowService(db)
        total_created = 0

        for org in organisations:
            existing_count = db.query(WorkflowEtape).filter(
                WorkflowEtape.organisation_id == org.id,
                WorkflowEtape.actif == True,
            ).count()
            print(f"Organisation ID={org.id} ({org.nom} - {org.code}) : {existing_count} étape(s) existante(s).")

            res = workflow_service.initialiser_workflow_par_defaut(organisation_id=org.id)
            db.commit()

            created_for_org = sum(res.values())
            total_created += created_for_org
            print(f" -> Étapes créées pour org {org.id} : {res} (total ajouté: {created_for_org})")

        total_etapes = db.query(WorkflowEtape).count()
        print(f"\n[OK] Rattrapage terminé avec succès.")
        print(f"Total étapes créées lors de cette exécution : {total_created}")
        print(f"Total global d'étapes dans la base : {total_etapes}")

    except Exception as e:
        db.rollback()
        print(f"[ERREUR] Échec du rattrapage des étapes de workflow : {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
