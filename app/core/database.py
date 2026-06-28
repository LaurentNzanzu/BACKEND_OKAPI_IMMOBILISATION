from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from .config import settings
import logging
import time

logger = logging.getLogger(__name__)

# 🔴 Configuration du pool optimisé pour BDD distante (Supabase Cloud)
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
    echo=False,
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Évite requêtes supplémentaires de rechargement
)

Base = declarative_base()


class LocalCache:
    """
    Cache en mémoire rapide pour éviter les requêtes BDD répétées
    sur les données fréquemment consultées (ex: authentification, sessions).
    """
    _cache = {}
    _ttl = {}

    @classmethod
    def get(cls, key: str):
        if key in cls._cache:
            if cls._ttl.get(key, 0) > time.time():
                return cls._cache[key]
            else:
                cls.delete(key)
        return None

    @classmethod
    def set(cls, key: str, value, ttl_seconds: int = 600):
        cls._cache[key] = value
        cls._ttl[key] = time.time() + ttl_seconds

    @classmethod
    def delete(cls, key: str):
        cls._cache.pop(key, None)
        cls._ttl.pop(key, None)

    @classmethod
    def clear(cls):
        cls._cache.clear()
        cls._ttl.clear()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_for_task() -> Session:
    """Session pour les tâches de fond (jobs CRON)."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def test_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur de connexion BDD : {e}")
        return False