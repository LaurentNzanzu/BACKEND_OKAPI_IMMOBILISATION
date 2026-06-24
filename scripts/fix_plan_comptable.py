# backend/scripts/fix_plan_comptable.py
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import SessionLocal
from sqlalchemy import text

def fix_plan_comptable():
    db = SessionLocal()
    try:
        # Vérifier si la colonne id a des valeurs NULL
        result = db.execute(text("SELECT COUNT(*) FROM plan_comptable WHERE id IS NULL")).scalar()
        print(f"Lignes avec id NULL: {result}")
        
        if result > 0:
            # Créer une séquence si elle n'existe pas
            db.execute(text("CREATE SEQUENCE IF NOT EXISTS plan_comptable_id_seq"))
            db.commit()
            
            # Mettre à jour les id NULL
            db.execute(text("""
                UPDATE plan_comptable 
                SET id = nextval('plan_comptable_id_seq') 
                WHERE id IS NULL
            """))
            db.commit()
            print(f"✅ {result} lignes mises à jour avec un id")
        
        # Rendre la colonne id NOT NULL
        db.execute(text("ALTER TABLE plan_comptable ALTER COLUMN id SET NOT NULL"))
        db.commit()
        
        # Ajouter la clé primaire si elle n'existe pas
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints 
                    WHERE table_name = 'plan_comptable' AND constraint_type = 'PRIMARY KEY'
                ) THEN
                    ALTER TABLE plan_comptable ADD PRIMARY KEY (id);
                END IF;
            END $$;
        """))
        db.commit()
        
        print("✅ Table plan_comptable corrigée")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_plan_comptable()