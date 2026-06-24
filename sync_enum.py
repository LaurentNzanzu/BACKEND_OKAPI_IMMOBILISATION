# sync_enum.py
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    # 1. Mettre à jour les données existantes
    print("Mise à jour des données existantes...")
    conn.execute(text("""
        UPDATE biens SET etat = 'NEUF' WHERE etat = 'neuf';
        UPDATE biens SET etat = 'BON' WHERE etat = 'bon';
        UPDATE biens SET etat = 'USAGE' WHERE etat = 'usage';
        UPDATE biens SET etat = 'PANNE' WHERE etat = 'panne';
        UPDATE biens SET etat = 'REFORME' WHERE etat = 'reforme';
        UPDATE biens SET etat = 'MAINTENANCE' WHERE etat = 'maintenance';
    """))
    
    # 2. Recréer l'enum avec les bonnes valeurs
    print("Re-création de l'enum...")
    conn.execute(text("DROP TYPE IF EXISTS etatbien CASCADE;"))
    conn.execute(text("""
        CREATE TYPE etatbien AS ENUM (
            'NEUF', 'BON', 'USAGE', 'PANNE', 'REFORME', 'MAINTENANCE', 'EN_TEST'
        );
    """))
    
    conn.commit()
    print("✅ Synchronisation terminée !")