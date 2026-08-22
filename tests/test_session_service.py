import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.utilisateur import Utilisateur
from app.models.session import SessionUtilisateur
from app.services.session_service import SessionService
from app.core.database import Base
from app.core.security import create_refresh_token

# Configuration de test
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db_session):
    user = Utilisateur(
        email="test@example.com",
        nom="Test",
        prenom="User",
        mot_de_passe="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_session(db_session, test_user):
    """Test de création de session."""
    refresh_token = create_refresh_token(test_user.id)
    
    session = SessionService.create_session(
        db=db_session,
        user_id=test_user.id,
        refresh_token=refresh_token,
        user_agent="Mozilla/5.0 Test",
        ip_address="127.0.0.1"
    )
    
    assert session is not None
    assert session.session_uuid is not None
    assert session.user_id == test_user.id
    assert not session.est_revoquee
    assert session.refresh_token_hash is not None


def test_session_limit(db_session, test_user):
    """Test de la limite de sessions simultanées."""
    # Créer 6 sessions (limite = 5)
    for i in range(6):
        refresh_token = create_refresh_token(test_user.id)
        session = SessionService.create_session(
            db=db_session,
            user_id=test_user.id,
            refresh_token=refresh_token,
            user_agent=f"Test Agent {i}",
            ip_address="127.0.0.1"
        )
    
    # Vérifier que 6 sessions ont été créées
    all_sessions = SessionService.get_user_all_sessions(db_session, test_user.id)
    assert len(all_sessions) == 6
    
    # Vérifier que 5 sont actives
    active_sessions = SessionService.get_user_active_sessions(db_session, test_user.id)
    assert len(active_sessions) == 5


def test_revoke_session(db_session, test_user):
    """Test de révocation de session."""
    refresh_token = create_refresh_token(test_user.id)
    session = SessionService.create_session(
        db=db_session,
        user_id=test_user.id,
        refresh_token=refresh_token,
        user_agent="Test Agent",
        ip_address="127.0.0.1"
    )
    
    # Vérifier que la session est active
    assert not session.est_revoquee
    
    # Révoquer la session
    success = SessionService.revoke_session(db_session, session.session_uuid)
    assert success
    
    # Vérifier que la session est révoquée
    db_session.refresh(session)
    assert session.est_revoquee
    assert session.date_fin is not None


def test_validate_session(db_session, test_user):
    """Test de validation de session."""
    refresh_token = create_refresh_token(test_user.id)
    session = SessionService.create_session(
        db=db_session,
        user_id=test_user.id,
        refresh_token=refresh_token,
        user_agent="Test Agent",
        ip_address="127.0.0.1"
    )
    
    # Valider avec le bon token
    is_valid = SessionService.validate_session(
        db_session, 
        session.session_uuid, 
        refresh_token=refresh_token
    )
    assert is_valid


def test_rotate_session(db_session, test_user):
    """Test de rotation de session."""
    refresh_token = create_refresh_token(test_user.id)
    session = SessionService.create_session(
        db=db_session,
        user_id=test_user.id,
        refresh_token=refresh_token,
        user_agent="Test Agent",
        ip_address="127.0.0.1"
    )
    
    old_hash = session.refresh_token_hash
    
    # Effectuer la rotation
    new_refresh_token = create_refresh_token(test_user.id)
    success = SessionService.rotate_session(
        db_session, 
        session.session_uuid, 
        new_refresh_token
    )
    assert success
    
    # Vérifier que le hash a changé
    db_session.refresh(session)
    assert session.refresh_token_hash != old_hash


def test_get_session_stats(db_session, test_user):
    """Test des statistiques de sessions."""
    # Créer quelques sessions
    for i in range(3):
        refresh_token = create_refresh_token(test_user.id)
        session = SessionService.create_session(
            db=db_session,
            user_id=test_user.id,
            refresh_token=refresh_token,
            user_agent=f"Test Agent {i}",
            ip_address="127.0.0.1"
        )
    
    stats = SessionService.get_session_stats(db_session)
    
    assert stats["total_sessions"] == 3
    assert stats["active_sessions"] == 3
    assert stats["revoked_sessions"] == 0


def test_cleanup_old_sessions(db_session, test_user):
    """Test du nettoyage des sessions anciennes."""
    refresh_token = create_refresh_token(test_user.id)
    session = SessionService.create_session(
        db=db_session,
        user_id=test_user.id,
        refresh_token=refresh_token,
        user_agent="Test Agent",
        ip_address="127.0.0.1"
    )
    
    # Modifier la date de dernière activité pour simuler une vieille session
    session.date_derniere_activite = datetime.utcnow() - timedelta(days=31)
    db_session.commit()
    
    # Exécuter le nettoyage
    deleted = SessionService.cleanup_old_sessions(
        db_session, 
        active_retention_days=30,
        revoked_retention_days=7
    )
    
    assert deleted == 1
    
    # Vérifier que la session a été supprimée
    remaining = db_session.query(SessionUtilisateur).all()
    assert len(remaining) == 0