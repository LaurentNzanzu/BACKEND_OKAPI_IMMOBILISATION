# backend/scripts/fix_plan_comptable_id.py
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import SessionLocal
from sqlalchemy import text

def fix_plan_comptable_id():
    db = SessionLocal()
    try:
        print("🔧 Correction de la table plan_comptable...")
        
        # 1. Vérifier si la colonne id existe
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'plan_comptable' AND column_name = 'id'
        """)).fetchone()
        
        if result:
            print(f"   Colonne id existe: {result}")
        
        # 2. Créer une séquence pour la colonne id
        print("   Création de la séquence...")
        db.execute(text("""
            CREATE SEQUENCE IF NOT EXISTS plan_comptable_id_seq 
            START WITH 1 
            INCREMENT BY 1 
            NO MINVALUE 
            NO MAXVALUE 
            CACHE 1
        """))
        db.commit()
        print("   ✅ Séquence créée")
        
        # 3. Mettre à jour les id NULL avec la séquence
        print("   Mise à jour des id NULL...")
        db.execute(text("""
            UPDATE plan_comptable 
            SET id = nextval('plan_comptable_id_seq') 
            WHERE id IS NULL
        """))
        db.commit()
        print("   ✅ Id NULL mis à jour")
        
        # 4. Rendre la colonne id NOT NULL
        print("   Rendre la colonne id NOT NULL...")
        db.execute(text("""
            ALTER TABLE plan_comptable 
            ALTER COLUMN id SET NOT NULL
        """))
        db.commit()
        print("   ✅ Colonne id NOT NULL")
        
        # 5. Définir la valeur par défaut de la colonne id
        print("   Définition de la valeur par défaut...")
        db.execute(text("""
            ALTER TABLE plan_comptable 
            ALTER COLUMN id SET DEFAULT nextval('plan_comptable_id_seq')
        """))
        db.commit()
        print("   ✅ Valeur par défaut définie")
        
        # 6. Ajouter la clé primaire si elle n'existe pas
        print("   Vérification de la clé primaire...")
        result = db.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'plan_comptable' 
            AND constraint_type = 'PRIMARY KEY'
        """)).fetchone()
        
        if not result:
            db.execute(text("""
                ALTER TABLE plan_comptable 
                ADD PRIMARY KEY (id)
            """))
            db.commit()
            print("   ✅ Clé primaire ajoutée")
        else:
            print("   ✅ Clé primaire existe déjà")
        
        print("\n✅ Table plan_comptable corrigée avec succès !")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    fix_plan_comptable_id()