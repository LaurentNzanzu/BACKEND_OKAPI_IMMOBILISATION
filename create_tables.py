# backend/create_tables.py
import sys
import os
from sqlalchemy import text

# Ajouter le chemin pour pouvoir importer
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import engine, Base
# Importer tous les modèles pour que metadata les trouve
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.models.bien import Bien
from app.models.caisse import Caisse
from app.models.amortissement import Amortissement
from app.models.ecriture_comptable import EcritureComptable
from app.models.mouvement_caisse import MouvementCaisse
from app.models.piece_justificative import PieceJustificative
from app.models.historique_statut_ecriture import HistoriqueStatutEcriture


def run():
    print("Création des tables manquantes...")
    Base.metadata.create_all(bind=engine)
    print("Tables créées.")

    print("Mise à jour des colonnes de ecritures_comptables...")
    columns_to_add = [
        ("piece_justificative_url", "VARCHAR(255)"),
        ("id_caisse", "INTEGER REFERENCES caisses(id_caisse) ON DELETE SET NULL"),
        ("statut_workflow", "VARCHAR(30) DEFAULT 'BROUILLON'"),
        ("date_verification_caisse", "TIMESTAMP"),
        ("date_validation_dg", "TIMESTAMP"),
        ("verrouille_definitivement", "BOOLEAN DEFAULT FALSE")
    ]

    with engine.begin() as conn:
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE ecritures_comptables ADD COLUMN {col_name} {col_type}"))
                print(f"Colonne '{col_name}' ajoutée à ecritures_comptables.")
            except Exception as e:
                print(f"Colonne '{col_name}' existe déjà ou erreur mineure : {e}")

    print("Mise à jour des colonnes de pieces_justificatives...")
    pj_columns = [
        ("id_mouvement", "INTEGER REFERENCES mouvements_caisse(id_mouvement) ON DELETE SET NULL"),
        ("type_document", "VARCHAR(10)"),
        ("numero_document", "VARCHAR(20)"),
        ("url_fichier", "VARCHAR(255)"),
        ("signature_caissier", "BOOLEAN DEFAULT FALSE"),
        ("signature_dg", "BOOLEAN DEFAULT FALSE"),
        ("date_signature_caissier", "TIMESTAMP"),
        ("date_signature_dg", "TIMESTAMP")
    ]

    with engine.begin() as conn:
        for col_name, col_type in pj_columns:
            try:
                conn.execute(text(f"ALTER TABLE pieces_justificatives ADD COLUMN {col_name} {col_type}"))
                print(f"Colonne '{col_name}' ajoutée à pieces_justificatives.")
            except Exception as e:
                print(f"Colonne '{col_name}' existe déjà ou erreur mineure : {e}")

    print("Migration terminée avec succès !")


if __name__ == "__main__":
    run()
