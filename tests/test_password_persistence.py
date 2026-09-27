"""Real ORM/HTTP password tests; isolated SQLite and in-memory cache doubles."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch("redis.Redis.ping", return_value=True):
    from app.api.endpoints import auth
from app.core import security, redis as cache_module
from app.core.database import Base, get_db, LocalCache
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.models.organisation import Organisation
from app.models.session import SessionUtilisateur

OLD = "TemporaryPass9!"
NEW = "PersonalPass8!"


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "passwords.db"),
                           connect_args={"check_same_thread": False})
    names = ["organisations", "roles", "permissions", "role_permissions", "utilisateurs", "sessions_utilisateurs"]
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in names])
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    old_hash = security.get_password_hash(OLD)
    with factory() as db:
        db.add(Role(id_role=1, nom="ADMIN"))
        for uid in (1, 2):
            db.add(Organisation(id=uid, nom=f"Org {uid}", code=f"O{uid}", email_admin=f"a{uid}@example.com"))
            db.add(Utilisateur(id=uid, organisation_id=uid, role_id=1, nom="Test", prenom="User",
                               email=f"a{uid}@example.com", mot_de_passe=old_hash,
                               est_actif=True, doit_changer_mot_de_passe=True))
        db.commit()
        db.add(SessionUtilisateur(user_id=1, session_uuid="test-session", refresh_token_hash="test-only"))
        db.commit()
    monkeypatch.setattr(security.redis_client, "is_blacklisted", Mock(return_value=False))
    monkeypatch.setattr(security.redis_client, "set_session", Mock(return_value=True))
    monkeypatch.setattr(security.redis_client, "revoke_session", Mock(return_value=True))
    monkeypatch.setattr(security.redis_client, "add_to_blacklist", Mock(return_value=True))
    LocalCache.clear()
    remote = {}
    monkeypatch.setattr(security.CacheService, "get", staticmethod(remote.get))
    monkeypatch.setattr(security.CacheService, "set", staticmethod(lambda key, value, ttl: remote.update({key: dict(value)})))
    monkeypatch.setattr(security.CacheService, "delete", staticmethod(lambda key: remote.pop(key, None)))
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    token = security.create_access_token(1, session_uuid="test-session")
    states = []
    original = auth._password_user
    def observe(db, user):
        states.append((inspect(user).transient, inspect(user).persistent))
        result = original(db, user)
        assert inspect(result).persistent and inspect(result).session is db
        return result
    monkeypatch.setattr(auth, "_password_user", observe)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, factory=factory, remote=remote, old_hash=old_hash,
                              headers={"Authorization": f"Bearer {token}"}, states=states)
    LocalCache.clear()
    engine.dispose()


def warm(w, mode):
    if mode == "miss":
        return
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        # Simuler les snapshots laissés par un worker de l'ancienne version.
        snapshot = {"id": user.id, "organisation_id": user.organisation_id,
                    "role_id": user.role_id, "role_nom": user.role.nom,
                    "est_actif": user.est_actif,
                    "doit_changer_mot_de_passe": user.doit_changer_mot_de_passe}
    key = security._build_cache_key(1)
    LocalCache.set(key, dict(snapshot))
    w.remote[key] = dict(snapshot)
    if mode == "redis":
        LocalCache.clear()


def change(w, endpoint, old=OLD):
    body = {"nouveau_mot_de_passe": NEW}
    if endpoint == "change-password":
        body["ancien_mot_de_passe"] = old
    return w.client.post("/api/v1/auth/" + endpoint, json=body, headers=w.headers)


@pytest.mark.parametrize("mode", ["miss", "local", "redis"])
@pytest.mark.parametrize("endpoint", ["change-password", "force-change-password"])
def test_persist_and_invalidate(workflow, mode, endpoint, monkeypatch):
    w = workflow
    warm(w, mode)
    real_invalidate = auth.invalidate_user_cache
    def invalidate(uid):
        # Independent session proves commit visibility, not just identity-map state.
        with w.factory() as db:
            saved = db.get(Utilisateur, uid)
            assert security.verify_password(NEW, saved.mot_de_passe)
            assert saved.doit_changer_mot_de_passe is False
        return real_invalidate(uid)
    spy = Mock(side_effect=invalidate)
    monkeypatch.setattr(auth, "invalidate_user_cache", spy)
    response = change(w, endpoint)
    assert response.status_code == 200, response.text
    assert w.states == [(False, True)]
    spy.assert_called_once_with(1)
    key = security._build_cache_key(1)
    assert LocalCache.get(key) is None and key not in w.remote
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        saved_hash = user.mot_de_passe
        assert not security.verify_password(OLD, user.mot_de_passe)
        assert user.organisation_id == 1 and user.role_id == 1
        assert db.get(Utilisateur, 2).mot_de_passe == w.old_hash
    me = w.client.get("/api/v1/auth/me", headers=w.headers)
    assert me.status_code == 200
    assert me.json()["doit_changer_mot_de_passe"] is False
    assert key not in w.remote and LocalCache.get(key) is None
    assert saved_hash not in me.text
    assert saved_hash not in response.text
    assert w.old_hash not in me.text and NEW not in me.text
    assert change(w, "force-change-password").status_code == 400


@pytest.mark.parametrize("mode", ["miss", "local", "redis"])
@pytest.mark.parametrize("endpoint", ["change-password", "force-change-password"])
@pytest.mark.parametrize("failure", ["flush", "commit", "verification"])
def test_transaction_failure_rolls_back(workflow, mode, endpoint, failure, monkeypatch):
    w = workflow
    warm(w, mode)
    invalidate = Mock()
    monkeypatch.setattr(auth, "invalidate_user_cache", invalidate)
    if failure == "verification":
        real_refresh = Session.refresh
        def refresh(db, user, *args, **kwargs):
            real_refresh(db, user, *args, **kwargs)
            user.doit_changer_mot_de_passe = True
        monkeypatch.setattr(Session, "refresh", refresh)
    else:
        monkeypatch.setattr(Session, failure, Mock(side_effect=RuntimeError("simulated database failure")))
    assert change(w, endpoint).status_code == 500
    invalidate.assert_not_called()
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        assert user.mot_de_passe == w.old_hash
        assert user.doit_changer_mot_de_passe is True


@pytest.mark.parametrize("endpoint", ["change-password", "force-change-password"])
@pytest.mark.parametrize("failure", ["false", "exception"])
def test_cache_failure_does_not_undo_committed_password(workflow, endpoint, failure, monkeypatch, caplog):
    w = workflow
    warm(w, "local")
    invalidator = Mock(return_value=False) if failure == "false" else Mock(side_effect=RuntimeError("cache unavailable"))
    monkeypatch.setattr(auth, "invalidate_user_cache", invalidator)
    assert change(w, endpoint).status_code == 200
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        assert security.verify_password(NEW, user.mot_de_passe)
        assert user.doit_changer_mot_de_passe is False
        assert user.mot_de_passe not in caplog.text
    assert "invalidation" in caplog.text
    # Stale true flag cannot authorize a second forced password change.
    assert change(w, "force-change-password").status_code == 400


@pytest.mark.parametrize("flag", [False, True])
def test_force_uses_database_flag_not_cache(workflow, flag):
    w = workflow
    warm(w, "local")
    LocalCache.get(security._build_cache_key(1))["doit_changer_mot_de_passe"] = not flag
    with w.factory() as db:
        db.get(Utilisateur, 1).doit_changer_mot_de_passe = flag
        db.commit()
    assert change(w, "force-change-password").status_code == (200 if flag else 400)


@pytest.mark.parametrize("endpoint", ["change-password", "force-change-password"])
def test_disabled_account_rejected_despite_cache(workflow, endpoint):
    w = workflow
    warm(w, "local")
    with w.factory() as db:
        db.get(Utilisateur, 1).est_actif = False
        db.commit()
    assert change(w, endpoint).status_code == 403
    with w.factory() as db:
        assert db.get(Utilisateur, 1).mot_de_passe == w.old_hash


def test_wrong_password_leaves_database_and_cache_unchanged(workflow, monkeypatch):
    w = workflow
    warm(w, "local")
    invalidate = Mock()
    monkeypatch.setattr(auth, "invalidate_user_cache", invalidate)
    assert change(w, "change-password", old="IncorrectPass9!").status_code == 400
    invalidate.assert_not_called()
    with w.factory() as db:
        assert db.get(Utilisateur, 1).mot_de_passe == w.old_hash


def test_detached_identity_is_reloaded_without_copying_stale_fields(workflow):
    w = workflow
    with w.factory() as db:
        identity = db.get(Utilisateur, 1)
    assert inspect(identity).detached
    identity.organisation_id = 2
    identity.nom = "Stale cached name"
    with w.factory() as db:
        user = auth._password_user(db, identity)
        assert user is not identity
        assert user.organisation_id == 1 and user.nom == "Test"
        auth._save_password(db, user, NEW)
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        assert security.verify_password(NEW, user.mot_de_passe)
        assert user.organisation_id == 1 and user.nom == "Test"


def test_invalidation_attempts_all_keys_after_failure(monkeypatch):
    local, remote = Mock(), Mock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(LocalCache, "delete", local)
    monkeypatch.setattr(security.CacheService, "delete", remote)
    assert security.invalidate_user_cache(42) is False
    assert [call.args[0] for call in local.call_args_list] == [security._build_cache_key(42), "user:42"]
    assert remote.call_count == 2


def test_redis_delete_reports_failure_and_clears_fallback(monkeypatch):
    monkeypatch.setattr(cache_module, "REDIS_AVAILABLE", True)
    monkeypatch.setattr(cache_module, "redis_client", Mock(delete=Mock(side_effect=RuntimeError("unavailable"))))
    monkeypatch.setattr(cache_module, "_in_memory_cache", {"user:test": ({}, 9999999999)})
    assert cache_module.CacheService.delete("user:test") is False
    assert "user:test" not in cache_module._in_memory_cache
