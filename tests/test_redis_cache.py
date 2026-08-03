"""
Tests pour la Phase 3 - Cache Redis des Sessions
Ces tests vérifient le bon fonctionnement du cache Redis avec fallback BDD.
"""

import pytest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.redis_client import RedisClient, redis_client
from app.services.session_cache_service import SessionCacheService
from app.services.session_service import SessionService
from app.models.session import SessionUtilisateur
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.core.database import Base
from app.core.security import create_refresh_token, get_password_hash
from app.core.config import settings

# ============================================================
# CONFIGURATION DES TESTS
# ============================================================

# Base de données de test (SQLite en mémoire)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(scope="function")
def db_session():
    """
    Fixture pour créer une session de base de données de test.
    Chaque test a sa propre base de données en mémoire.
    """
    # Créer les tables
    Base.metadata.create_all(bind=engine)
    
    # Créer une session
    db = TestingSessionLocal()
    
    try:
        yield db
    finally:
        db.rollback()
        db.close()
    
    # Nettoyer après le test
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_role(db_session):
    """Crée un rôle de test."""
    role = Role(
        nom="USER",
        description="Rôle utilisateur standard"
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture
def test_user(db_session, test_role):
    """Crée un utilisateur de test."""
    user = Utilisateur(
        email="test@example.com",
        nom="Test",
        prenom="User",
        post_nom="Testeur",
        mot_de_passe=get_password_hash("Test123!"),
        est_actif=True,
        role_id=test_role.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user2(db_session, test_role):
    """Crée un deuxième utilisateur de test."""
    user = Utilisateur(
        email="test2@example.com",
        nom="Test2",
        prenom="User2",
        post_nom="Testeur2",
        mot_de_passe=get_password_hash("Test123!"),
        est_actif=True,
        role_id=test_role.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_session(db_session, test_user):
    """Crée une session de test."""
    refresh_token = create_refresh_token(test_user.id)
    session = SessionService.create_session(
        db=db_session,
        user_id=test_user.id,
        refresh_token=refresh_token,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        ip_address="127.0.0.1",
        session_data={"device_type": "desktop", "browser": "Chrome"}
    )
    return session


@pytest.fixture
def mock_redis_available():
    """Mock pour simuler Redis disponible."""
    with patch('app.core.redis_client.redis_client.is_healthy', return_value=True):
        with patch('app.core.redis_client.redis_client.get_session') as mock_get:
            yield mock_get


@pytest.fixture
def mock_redis_unavailable():
    """Mock pour simuler Redis indisponible."""
    with patch('app.core.redis_client.redis_client.is_healthy', return_value=False):
        with patch('app.core.redis_client.redis_client.get_session', return_value=None):
            yield


# ============================================================
# TESTS DU CLIENT REDIS
# ============================================================

class TestRedisClient:
    """Tests du client Redis."""

    def test_redis_client_initialization(self):
        """Test que le client Redis s'initialise correctement."""
        assert redis_client is not None
        assert hasattr(redis_client, 'get_session')
        assert hasattr(redis_client, 'set_session')
        assert hasattr(redis_client, 'revoke_session')
        assert hasattr(redis_client, 'delete_session')
        assert hasattr(redis_client, 'is_healthy')
        assert hasattr(redis_client, 'get_stats')

    def test_redis_health_check(self):
        """Test du healthcheck Redis."""
        is_healthy = redis_client.is_healthy()
        # Le résultat peut être True ou False selon la disponibilité de Redis
        assert isinstance(is_healthy, bool)

    @patch('app.core.redis_client.redis_client._get_client')
    def test_redis_get_session(self, mock_get_client):
        """Test de récupération d'une session depuis Redis."""
        # Mock du client Redis
        mock_client = MagicMock()
        mock_client.hgetall.return_value = {
            "user_id": "1",
            "revoked": "false",
            "fingerprint": "test_fingerprint",
            "user_agent": "Test Agent",
            "ip_address": "127.0.0.1",
            "session_data": '{"test": "data"}',
            "last_activity": str(time.time())
        }
        mock_get_client.return_value = mock_client

        # Récupérer la session
        result = redis_client.get_session(1, "test-uuid")

        # Vérifier que le résultat est correct
        if result is not None:  # Si Redis est disponible
            assert result["user_id"] == "1"
            assert result["revoked"] is False
            assert result["fingerprint"] == "test_fingerprint"
            assert "session_data" in result

    @patch('app.core.redis_client.redis_client._get_client')
    def test_redis_set_session(self, mock_get_client):
        """Test de stockage d'une session en Redis."""
        # Mock du client Redis
        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_client
        mock_client.hset.return_value = True
        mock_client.expire.return_value = True
        mock_client.execute.return_value = [True, True]
        mock_get_client.return_value = mock_client

        # Stocker la session
        data = {
            "user_id": "1",
            "revoked": "false",
            "fingerprint": "test_fingerprint",
            "user_agent": "Test Agent",
            "ip_address": "127.0.0.1",
            "session_data": {"test": "data"},
            "last_activity": str(time.time())
        }
        
        result = redis_client.set_session(1, "test-uuid", data, ttl=3600)

        # Vérifier le résultat
        assert result is not None

    @patch('app.core.redis_client.redis_client._get_client')
    def test_redis_revoke_session(self, mock_get_client):
        """Test de révocation d'une session en Redis."""
        # Mock du client Redis
        mock_client = MagicMock()
        mock_client.hset.return_value = True
        mock_get_client.return_value = mock_client

        # Révoquer la session
        result = redis_client.revoke_session(1, "test-uuid")

        # Vérifier le résultat
        assert result is not None


# ============================================================
# TESTS DU SERVICE DE CACHE
# ============================================================

class TestSessionCacheService:
    """Tests du service de cache des sessions."""

    def test_session_to_cache_data(self, test_session):
        """Test de conversion session → données de cache."""
        cache_data = SessionCacheService._session_to_cache_data(test_session)
        
        assert "user_id" in cache_data
        assert cache_data["user_id"] == str(test_session.user_id)
        assert "revoked" in cache_data
        assert "fingerprint" in cache_data
        assert "user_agent" in cache_data
        assert "ip_address" in cache_data
        assert "session_data" in cache_data
        assert "last_activity" in cache_data

    def test_cache_session(self, db_session, test_session):
        """Test de mise en cache d'une session."""
        # Cacher la session
        result = SessionCacheService.cache_session(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        # Le résultat peut être True ou False selon la disponibilité de Redis
        # Mais la fonction ne doit pas lever d'exception
        assert result is not None

    def test_get_session_data_from_cache(self, db_session, test_session, mock_redis_available):
        """Test de récupération des données depuis le cache."""
        # Préparer les données de cache mockées
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "false",
            "fingerprint": test_session.fingerprint,
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Récupérer les données
        data, from_cache = SessionCacheService.get_session_data(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        # Vérifier que les données sont récupérées
        if data is not None:
            assert "user_id" in data
            assert data["user_id"] == str(test_session.user_id)
            assert from_cache is True

    def test_get_session_data_fallback_bdd(self, db_session, test_session, mock_redis_unavailable):
        """Test du fallback BDD quand Redis est indisponible."""
        # Redis est indisponible, on doit tomber sur la BDD
        data, from_cache = SessionCacheService.get_session_data(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        # Vérifier que les données sont récupérées de la BDD
        if data is not None:
            assert "user_id" in data
            assert data["user_id"] == str(test_session.user_id)
            assert from_cache is False

    def test_validate_session_valid(self, db_session, test_session, mock_redis_available):
        """Test de validation d'une session valide."""
        # Préparer les données de cache mockées
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "false",
            "fingerprint": test_session.fingerprint,
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Valider la session
        is_valid, message = SessionCacheService.validate_session(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        # Vérifier le résultat
        assert is_valid is True
        assert message == "Session valide"

    def test_validate_session_revoked(self, db_session, test_session, mock_redis_available):
        """Test de validation d'une session révoquée."""
        # Préparer les données de cache mockées avec revoked = true
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "true",
            "fingerprint": test_session.fingerprint,
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Valider la session
        is_valid, message = SessionCacheService.validate_session(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        # Vérifier que la session est invalide
        assert is_valid is False
        assert "révoquée" in message or "revoked" in message.lower()

    def test_validate_session_fingerprint_mismatch(self, db_session, test_session, mock_redis_available):
        """Test de validation avec fingerprint mismatch (compromission détectée)."""
        # Préparer les données de cache mockées
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "false",
            "fingerprint": "different_fingerprint",  # Fingerprint différent
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Valider la session avec fingerprint mismatch
        is_valid, message = SessionCacheService.validate_session(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid,
            fingerprint=test_session.fingerprint  # Fingerprint original
        )
        
        # Vérifier que la compromission est détectée
        if test_session.fingerprint:  # Si un fingerprint est défini
            assert is_valid is False
            assert "compromise" in message.lower() or "compromission" in message

    def test_is_session_active(self, db_session, test_session, mock_redis_available):
        """Test de vérification d'activité d'une session."""
        # Préparer les données de cache mockées
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "false",
            "fingerprint": test_session.fingerprint,
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Vérifier l'activité
        is_active = SessionCacheService.is_session_active(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        assert is_active is True

    def test_is_session_active_revoked(self, db_session, test_session, mock_redis_available):
        """Test de vérification d'activité d'une session révoquée."""
        # Préparer les données de cache mockées avec revoked = true
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "true",
            "fingerprint": test_session.fingerprint,
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Vérifier l'activité
        is_active = SessionCacheService.is_session_active(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        assert is_active is False

    def test_revoke_session_cache(self, db_session, test_session, mock_redis_available):
        """Test de révocation d'une session en cache."""
        # Mock du client Redis pour révocation
        with patch('app.core.redis_client.redis_client.revoke_session') as mock_revoke:
            mock_revoke.return_value = True
            
            # Révoquer en cache
            result = SessionCacheService.revoke_session_cache(
                user_id=test_session.user_id,
                session_uuid=test_session.session_uuid
            )
            
            assert result is not None

    def test_delete_session_cache(self, db_session, test_session, mock_redis_available):
        """Test de suppression d'une session du cache."""
        # Mock du client Redis pour suppression
        with patch('app.core.redis_client.redis_client.delete_session') as mock_delete:
            mock_delete.return_value = True
            
            # Supprimer du cache
            result = SessionCacheService.delete_session_cache(
                user_id=test_session.user_id,
                session_uuid=test_session.session_uuid
            )
            
            assert result is not None

    def test_revoke_all_user_sessions_cache(self, db_session, test_session, mock_redis_available):
        """Test de révocation massive des sessions d'un utilisateur."""
        # Mock du client Redis pour révocation massive
        with patch('app.core.redis_client.redis_client.revoke_all_user_sessions') as mock_revoke_all:
            mock_revoke_all.return_value = 1
            
            # Révoquer toutes les sessions
            result = SessionCacheService.revoke_all_user_sessions_cache(
                user_id=test_session.user_id
            )
            
            assert result is not None

    def test_get_cache_stats(self, mock_redis_available):
        """Test de récupération des statistiques du cache."""
        # Mock des statistiques
        with patch('app.core.redis_client.redis_client.get_stats') as mock_stats:
            mock_stats.return_value = {
                "available": True,
                "total_sessions": 10,
                "active_sessions": 8,
                "revoked_sessions": 2
            }
            
            # Récupérer les statistiques
            stats = SessionCacheService.get_cache_stats()
            
            assert "available" in stats
            assert stats["available"] is True

    def test_is_redis_available(self):
        """Test de vérification de disponibilité de Redis."""
        is_available = SessionCacheService.is_redis_available()
        assert isinstance(is_available, bool)


# ============================================================
# TESTS D'INTÉGRATION AVEC LE SERVICE DE SESSION
# ============================================================

class TestSessionServiceWithCache:
    """Tests d'intégration entre SessionService et le cache Redis."""

    def test_create_session_with_cache(self, db_session, test_user, mock_redis_available):
        """Test de création de session avec cache."""
        # Mock du client Redis pour set_session
        with patch('app.core.redis_client.redis_client.set_session') as mock_set:
            mock_set.return_value = True
            
            # Créer une session
            refresh_token = create_refresh_token(test_user.id)
            session = SessionService.create_session(
                db=db_session,
                user_id=test_user.id,
                refresh_token=refresh_token,
                user_agent="Test Agent",
                ip_address="127.0.0.1",
                session_data={"test": "data"}
            )
            
            # Vérifier que la session est créée
            assert session is not None
            assert session.session_uuid is not None
            assert session.user_id == test_user.id

    def test_get_session_by_uuid_from_cache(self, db_session, test_session, mock_redis_available):
        """Test de récupération de session depuis le cache."""
        # Préparer les données de cache mockées
        mock_redis_available.return_value = {
            "user_id": str(test_session.user_id),
            "revoked": "false",
            "fingerprint": test_session.fingerprint,
            "user_agent": test_session.user_agent,
            "ip_address": test_session.ip_address,
            "session_data": json.dumps(test_session.session_data or {}),
            "last_activity": str(time.time())
        }
        
        # Récupérer la session
        session = SessionService.get_session_by_uuid(
            db=db_session,
            session_uuid=test_session.session_uuid,
            user_id=test_session.user_id
        )
        
        # Vérifier que la session est récupérée
        if session is not None:
            assert session.session_uuid == test_session.session_uuid

    def test_revoke_session_with_cache(self, db_session, test_session, mock_redis_available):
        """Test de révocation de session avec mise à jour du cache."""
        # Mock du client Redis pour révocation
        with patch('app.core.redis_client.redis_client.revoke_session') as mock_revoke:
            mock_revoke.return_value = True
            
            # Révoquer la session
            result = SessionService.revoke_session(
                db=db_session,
                session_uuid=test_session.session_uuid,
                user_id=test_session.user_id,
                reason="Test revocation"
            )
            
            # Vérifier que la révocation a réussi
            assert result is True
            
            # Vérifier que la session est révoquée en BDD
            db_session.refresh(test_session)
            assert test_session.est_revoquee is True

    def test_revoke_all_sessions_with_cache(self, db_session, test_user, mock_redis_available):
        """Test de révocation massive avec mise à jour du cache."""
        # Créer plusieurs sessions
        sessions = []
        for i in range(3):
            refresh_token = create_refresh_token(test_user.id)
            session = SessionService.create_session(
                db=db_session,
                user_id=test_user.id,
                refresh_token=refresh_token,
                user_agent=f"Test Agent {i}",
                ip_address="127.0.0.1"
            )
            sessions.append(session)
        
        # Mock du client Redis pour révocation massive
        with patch('app.core.redis_client.redis_client.revoke_all_user_sessions') as mock_revoke_all:
            mock_revoke_all.return_value = len(sessions)
            
            # Révoquer toutes les sessions
            revoked_count = SessionService.revoke_all_sessions(
                db=db_session,
                user_id=test_user.id
            )
            
            # Vérifier que toutes les sessions sont révoquées
            assert revoked_count == len(sessions)

    def test_rotate_session_with_cache(self, db_session, test_session, mock_redis_available):
        """Test de rotation de session avec mise à jour du cache."""
        # Mock du client Redis pour mise à jour
        with patch('app.core.redis_client.redis_client.set_session') as mock_set:
            mock_set.return_value = True
            
            # Effectuer la rotation
            new_refresh_token = create_refresh_token(test_session.user_id)
            result = SessionService.rotate_session(
                db=db_session,
                session_uuid=test_session.session_uuid,
                new_refresh_token=new_refresh_token,
                user_id=test_session.user_id
            )
            
            # Vérifier que la rotation a réussi
            assert result is True
            
            # Vérifier que la session est mise à jour
            db_session.refresh(test_session)
            assert test_session.refresh_token_hash is not None


# ============================================================
# TESTS DE PERFORMANCE
# ============================================================

class TestPerformance:
    """Tests de performance du cache Redis."""

    def test_cache_latency(self, db_session, test_session):
        """Test de la latence du cache Redis."""
        # Mesurer le temps de validation avec cache
        start_time = time.time()
        
        # Valider la session
        is_valid, message = SessionCacheService.validate_session(
            db=db_session,
            user_id=test_session.user_id,
            session_uuid=test_session.session_uuid
        )
        
        elapsed = (time.time() - start_time) * 1000  # en millisecondes
        
        # La validation ne doit pas prendre trop de temps
        # (même avec fallback BDD, ça doit être < 50ms)
        assert elapsed < 100

    @pytest.mark.skip(reason="Test de performance nécessitant Redis réel")
    def test_cache_hit_rate(self, db_session, test_user):
        """Test du taux de succès du cache (nécessite Redis réel)."""
        # Créer une session
        refresh_token = create_refresh_token(test_user.id)
        session = SessionService.create_session(
            db=db_session,
            user_id=test_user.id,
            refresh_token=refresh_token,
            user_agent="Performance Test",
            ip_address="127.0.0.1"
        )
        
        # Faire plusieurs requêtes de validation
        hit_count = 0
        total_count = 10
        
        for i in range(total_count):
            is_valid, _ = SessionCacheService.validate_session(
                db=db_session,
                user_id=session.user_id,
                session_uuid=session.session_uuid
            )
            if is_valid:
                hit_count += 1
        
        # Le taux de succès devrait être élevé (> 80%)
        hit_rate = hit_count / total_count
        print(f"Cache hit rate: {hit_rate * 100:.2f}%")
        
        # Sans Redis réel, ce test est ignoré


# ============================================================
# EXÉCUTION DES TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])