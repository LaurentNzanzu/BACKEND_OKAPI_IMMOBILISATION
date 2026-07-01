# scratch/update_check_constraint.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    try:
        # Dropper la contrainte existante
        conn.execute(text("ALTER TABLE ecritures_comptables DROP CONSTRAINT IF EXISTS chk_ecritures_statut"))
        print("Dropped old constraint chk_ecritures_statut.")
        
        # Recréer la contrainte avec les nouveaux statuts
        conn.execute(text("""
            ALTER TABLE ecritures_comptables 
            ADD CONSTRAINT chk_ecritures_statut 
            CHECK (statut IN (
                'BROUILLON', 
                'VALIDEE', 
                'REJETEE', 
                'MODIFIEE', 
                'EN_ATTENTE_PAIEMENT', 
                'EN_ATTENTE_FONDS', 
                'CAISSE_VALIDE', 
                'DG_VALIDE'
            ))
        """))
        print("Created updated constraint chk_ecritures_statut.")
    except Exception as e:
        print("Error updating constraint:", e)
