# backend/fix_enum_data.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from sqlalchemy import text

def fix_enum_values():
    db = SessionLocal()
    try:
        print("=== Correction des valeurs ENUM ===\n")
        
        # 1. Afficher les valeurs actuelles
        result = db.execute(text("SELECT id_piece, compatible_avec FROM pieces_rechange"))
        print("Valeurs actuelles:")
        rows = result.fetchall()
        for row in rows:
            print(f"  ID: {row[0]}, Compatible: {row[1]}")
        
        if not rows:
            print("Aucune donnée à corriger")
            return
        
        # 2. Convertir en majuscules en utilisant une colonne temporaire
        print("\nConversion en majuscules...")
        
        # Ajouter une colonne temporaire
        db.execute(text("""
            ALTER TABLE pieces_rechange 
            ADD COLUMN compatible_avec_temp VARCHAR(50)
        """))
        
        # Copier les données converties
        db.execute(text("""
            UPDATE pieces_rechange 
            SET compatible_avec_temp = UPPER(compatible_avec::text)
        """))
        
        # Supprimer l'ancienne colonne
        db.execute(text("""
            ALTER TABLE pieces_rechange 
            DROP COLUMN compatible_avec
        """))
        
        # Recréer la colonne avec le bon type
        db.execute(text("""
            ALTER TABLE pieces_rechange 
            ADD COLUMN compatible_avec typecompatible
        """))
        
        # Remettre les données
        db.execute(text("""
            UPDATE pieces_rechange 
            SET compatible_avec = compatible_avec_temp::typecompatible
        """))
        
        # Supprimer la colonne temporaire
        db.execute(text("""
            ALTER TABLE pieces_rechange 
            DROP COLUMN compatible_avec_temp
        """))
        
        db.commit()
        
        # 3. Vérifier après correction
        result = db.execute(text("SELECT compatible_avec, COUNT(*) FROM pieces_rechange GROUP BY compatible_avec"))
        print("\nValeurs après correction:")
        for row in result:
            print(f"  {row[0]}: {row[1]} pièces")
        
        print("\n✅ Correction terminée avec succès!")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_enum_values()