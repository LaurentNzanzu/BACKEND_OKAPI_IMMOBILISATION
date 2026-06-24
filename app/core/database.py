from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from .config import settings

# Création du moteur de connexion
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,        # Vérifie la connexion avant utilisation
    pool_size=5,               # Nombre de connexions gardées en pool
    max_overflow=10            # Connexions supplémentaires autorisées
)

# Session factory pour interagir avec la BDD
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

# Base pour les modèles SQLAlchemy
Base = declarative_base()

# Dépendance FastAPI : fournit une session DB par requête
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Fonction utilitaire pour tester la connexion
def test_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"❌ Erreur de connexion : {e}")
        return False