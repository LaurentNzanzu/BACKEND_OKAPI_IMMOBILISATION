"""Database authority despite legacy snapshots, with real ORM and HTTP guards."""
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, inspect
from sqlalchemy.orm import Session

from test_password_persistence import workflow, warm, OLD
from app.api.endpoints import utilisateurs
from app.core import security
from app.core.database import LocalCache
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.models.permission import Permission


def load(w, db):
    return security.get_current_user(None, db, w.headers["Authorization"].split()[1])


@pytest.mark.parametrize("mode", ["miss", "local", "redis"])
def test_database_instance_and_bounded_queries(workflow, mode, monkeypatch):
    w = workflow
    warm(w, mode)
    # Cache must neither be consulted nor receive hashes, tokens or ORM objects.
    for cache in (LocalCache, security.CacheService):
        monkeypatch.setattr(cache, "get", Mock(side_effect=AssertionError("cache read")))
        monkeypatch.setattr(cache, "set", Mock(side_effect=AssertionError("cache write")))
    initialized, statements = [], []
    def init(target, args, kwargs):
        initialized.append(target)
    def sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(Utilisateur, "init", init)
    engine = w.factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", sql)
    try:
        with w.factory() as db:
            user = load(w, db)
            assert inspect(user).persistent and inspect(user).session is db
            assert user.mot_de_passe == w.old_hash
            assert user.role.nom == "ADMIN" and user.organisation_id == 1
            assert user.role.permissions == []
            assert "utilisateurs" in inspect(user.role).unloaded
            assert user.is_org_admin and not user.is_platform_admin
        assert initialized == []  # ORM materialization bypasses the constructor.
        assert len(statements) == 3  # SQL session revocation, user + role, permissions.
    finally:
        event.remove(Utilisateur, "init", init)
        event.remove(engine, "before_cursor_execute", sql)


@pytest.mark.parametrize("mode", ["local", "redis"])
@pytest.mark.parametrize("change", ["disabled", "deleted", "role", "organisation", "profile"])
def test_stale_snapshot_never_overrides_database(workflow, mode, change):
    w = workflow
    warm(w, mode)
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        if change == "disabled":
            user.est_actif = False
        elif change == "deleted":
            db.execute(delete(Utilisateur).where(Utilisateur.id == 1))
        elif change == "role":
            db.add(Role(id_role=2, nom="COMPTABLE"))
            user.role_id = 2
        elif change == "organisation":
            user.organisation_id = 2
        else:
            user.nom = "Updated"
            user.telephone = "+243970123456"
        db.commit()
    # Keep both old caches intact, as on another worker whose invalidation failed.
    with w.factory() as db:
        if change in ("disabled", "deleted"):
            with pytest.raises(HTTPException) as exc:
                load(w, db)
            assert exc.value.status_code == (403 if change == "disabled" else 401)
        else:
            user = load(w, db)
            if change == "role":
                assert user.role.nom == "COMPTABLE" and not user.has_role("ADMIN")
            elif change == "organisation":
                assert user.organisation_id == 2 and not user.is_platform_admin
            else:
                assert user.nom == "Updated" and user.telephone == "+243970123456"


def test_existing_identity_and_permissions_are_refreshed(workflow):
    w = workflow
    with w.factory() as db:
        role = Role(id_role=2, nom="COMPTABLE")
        role.permissions.append(Permission(id_permission=1, nom="READ_TEST", module="TEST", action="READ", actif=True))
        db.add(role)
        db.get(Utilisateur, 1).role_id = 2
        db.commit()
    with w.factory() as db:
        first = load(w, db)
        assert first.has_permission("READ_TEST")
        db.commit()  # Same identity map, fresh transaction (production expire_on_commit=False).
        with w.factory() as writer:
            writer.get(Permission, 1).actif = False
            writer.get(Utilisateur, 1).organisation_id = 2
            writer.commit()
        second = load(w, db)
        assert second is first and second.organisation_id == 2
        assert not second.has_permission("READ_TEST")


def test_old_worker_cannot_reintroduce_platform_or_other_tenant_access(workflow):
    w = workflow
    w.client.app.include_router(utilisateurs.router, prefix="/api/v1")
    warm(w, "local")
    key = security._build_cache_key(1)
    stale_worker = dict(LocalCache.get(key))
    stale_worker.update(organisation_id=None, id=2, role_nom="ADMIN")
    for _ in range(2):
        LocalCache.set(key, dict(stale_worker))
        w.remote[key] = dict(stale_worker)
        response = w.client.get("/api/v1/utilisateurs", headers=w.headers)
        assert response.status_code == 200
        assert [u["id"] for u in response.json()["items"]] == [1]
        assert w.client.get("/api/v1/utilisateurs/2", headers=w.headers).status_code == 403
        assert security.invalidate_user_cache(1)


def test_http_guard_uses_new_role_and_organisation(workflow):
    w = workflow
    w.client.app.include_router(utilisateurs.router, prefix="/api/v1")
    warm(w, "local")
    with w.factory() as db:
        db.get(Utilisateur, 1).organisation_id = 2
        db.commit()
    assert w.client.get("/api/v1/utilisateurs/2", headers=w.headers).status_code == 200
    with w.factory() as db:
        db.add(Role(id_role=2, nom="COMPTABLE"))
        db.get(Utilisateur, 1).role_id = 2
        db.commit()
    assert w.client.get("/api/v1/utilisateurs", headers=w.headers).status_code == 403


def test_redis_outage_does_not_affect_authentication(workflow, monkeypatch):
    w = workflow
    warm(w, "local")
    for name in ("get", "set", "delete"):
        monkeypatch.setattr(security.CacheService, name, Mock(side_effect=ConnectionError("Redis down")))
    with w.factory() as db:
        assert load(w, db).id == 1
    with w.factory() as db:
        db.get(Utilisateur, 1).est_actif = False
        db.commit()
    assert w.client.get("/api/v1/auth/me", headers=w.headers).status_code == 403


def test_database_failure_never_falls_back_to_cached_authorization(workflow, monkeypatch):
    w = workflow
    warm(w, "local")
    with w.factory() as db:
        monkeypatch.setattr(db, "query", Mock(side_effect=RuntimeError("database unavailable")))
        with pytest.raises(RuntimeError, match="database unavailable"):
            load(w, db)


@pytest.fixture
def mutations(workflow, monkeypatch):
    w = workflow
    w.client.app.include_router(utilisateurs.router, prefix="/api/v1")
    monkeypatch.setattr(utilisateurs.AuditService, "log_action", Mock())
    with w.factory() as db:
        db.get(Utilisateur, 2).organisation_id = 1
        db.add(Role(id_role=2, nom="COMPTABLE"))
        db.commit()
    return w


def mutate(w, operation):
    if operation == "profile":
        return w.client.patch("/api/v1/utilisateurs/1/profil", headers=w.headers,
                              json={"nom": "Updated", "ancien_mot_de_passe": OLD,
                                    "nouveau_mot_de_passe": "ProfilePass9!"})
    if operation == "toggle":
        return w.client.patch("/api/v1/utilisateurs/2/toggle-actif", headers=w.headers)
    return w.client.put("/api/v1/utilisateurs/2", headers=w.headers,
                        json={"role_id": 2, "nom": "Updated"})


@pytest.mark.parametrize("operation", ["profile", "toggle", "update"])
def test_mutations_invalidate_both_caches_only_after_commit(mutations, operation, monkeypatch):
    w = mutations
    uid = 1 if operation == "profile" else 2
    keys = [security._build_cache_key(uid), security._build_cache_key_legacy(uid)]
    for key in keys:
        LocalCache.set(key, {"id": uid})
        w.remote[key] = {"id": uid}
    original = utilisateurs.invalidate_user_cache
    def invalidate(user_id):
        with w.factory() as db:
            user = db.get(Utilisateur, user_id)
            if operation == "toggle":
                assert user.est_actif is False
            else:
                assert user.nom == "Updated"
            if operation == "profile":
                assert security.verify_password("ProfilePass9!", user.mot_de_passe)
            if operation == "update":
                assert user.role_id == 2
        return original(user_id)
    spy = Mock(side_effect=invalidate)
    monkeypatch.setattr(utilisateurs, "invalidate_user_cache", spy)
    response = mutate(w, operation)
    assert response.status_code == 200, response.text
    spy.assert_called_once_with(uid)
    for key in keys:
        assert LocalCache.get(key) is None and key not in w.remote
    assert w.old_hash not in response.text


@pytest.mark.parametrize("operation", ["profile", "toggle", "update"])
def test_failed_mutation_does_not_invalidate(mutations, operation, monkeypatch):
    w = mutations
    spy = Mock()
    monkeypatch.setattr(utilisateurs, "invalidate_user_cache", spy)
    monkeypatch.setattr(Session, "commit", Mock(side_effect=RuntimeError("database failure")))
    assert mutate(w, operation).status_code == 500
    spy.assert_not_called()
    with w.factory() as db:
        user = db.get(Utilisateur, 1 if operation == "profile" else 2)
        assert user.nom == "Test" and user.est_actif and user.role_id == 1
        assert user.mot_de_passe == w.old_hash


@pytest.mark.parametrize("operation", ["profile", "toggle", "update"])
def test_cache_delete_failure_does_not_change_success(mutations, operation, monkeypatch, caplog):
    monkeypatch.setattr(security.CacheService, "delete", Mock(side_effect=ConnectionError("Redis down")))
    assert mutate(mutations, operation).status_code == 200
    assert "invalidation" in caplog.text
