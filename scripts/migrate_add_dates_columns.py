# backend/scripts/migrate_add_dates_columns.py
"""
Script pour ajouter les colonnes date_sortie et date_retour à la table biens
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_missing_columns():
    """Ajoute les colonnes manquantes à la table biens"""
    db = SessionLocal()
    try:
        # Vérifier si la colonne date_sortie existe
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'biens' AND column_name = 'date_sortie'
        """))
        
        if result.rowcount == 0:
            logger.info("Ajout de la colonne date_sortie...")
            db.execute(text("""
                ALTER TABLE biens 
                ADD COLUMN date_sortie TIMESTAMP NULL
            """))
            db.commit()
            logger.info("✅ Colonne date_sortie ajoutée")
        else:
            logger.info("✅ Colonne date_sortie existe déjà")
        
        # Vérifier si la colonne date_retour existe
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'biens' AND column_name = 'date_retour'
        """))
        
        if result.rowcount == 0:
            logger.info("Ajout de la colonne date_retour...")
            db.execute(text("""
                ALTER TABLE biens 
                ADD COLUMN date_retour TIMESTAMP NULL
            """))
            db.commit()
            logger.info("✅ Colonne date_retour ajoutée")
        else:
            logger.info("✅ Colonne date_retour existe déjà")
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de la migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("Début de la migration...")
    add_missing_columns()
    logger.info("Migration terminée !")