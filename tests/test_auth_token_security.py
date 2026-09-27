"""JWT/reset/revocation integration tests; SQLite only, SMTP and Redis isolated."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs
from unittest.mock import Mock
import uuid
import time

import pytest
from jose import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from redis.exceptions import ConnectionError as RedisConnectionError

from test_password_persistence import workflow, OLD, NEW, change
from app.api.endpoints import auth, utilisateurs
from app.core import security
from app.core.cookies import REFRESH_COOKIE
from app.core.database import get_db
from app.models.utilisateur import Utilisateur
from app.models.session import SessionUtilisateur
from app.services.session_service import SessionService
from app.services.session_cache_service import SessionCacheService
from app.middleware import session_middleware

send_reset_email = auth.EmailService.send_password_reset_email


@pytest.fixture
def secured(workflow, monkeypatch):
    w = workflow
    monkeypatch.setattr(auth.AuditService, "log_login", Mock())
    monkeypatch.setattr(auth.AuditService, "log_logout", Mock())
    monkeypatch.setattr(auth.EmailService, "is_configured", Mock(return_value=True))
    sent = []
    monkeypatch.setattr(auth.EmailService, "send_password_reset_email",
                        lambda email, link: sent.append((email, link)) or True)
    w.sent = sent
    return w


def reset_token(w):
    with w.factory() as db:
        return security.create_password_reset_token(db.get(Utilisateur, 1))


def reset(w, token, password=NEW):
    return w.client.post("/api/v1/auth/reset-password", json={"token": token, "nouveau_mot_de_passe": password})


def pair(w, uid=1):
    sid = str(uuid.uuid4())
    access = security.create_access_token(uid, session_uuid=sid)
    refresh = security.create_refresh_token(uid, session_uuid=sid)
    with w.factory() as db:
        db.add(SessionUtilisateur(user_id=uid, session_uuid=sid,
                                 refresh_token_hash=SessionService.hash_refresh_token(refresh)))
        db.commit()
    return SimpleNamespace(sid=sid, access=access, refresh=refresh,
                           headers={"Authorization": "Bearer " + access})


def refresh(w, token):
    w.client.cookies.clear()
    return w.client.post("/api/v1/auth/refresh", headers={"Authorization": "Bearer " + token})


@pytest.mark.parametrize("kind", ["access", "refresh", "expired", "invalid", "wrong_stamp"])
def test_reset_rejects_wrong_tokens(secured, kind):
    w = secured
    if kind in ("access", "refresh"):
        token = getattr(pair(w), kind)
    elif kind == "invalid":
        token = "invalid-token"
    else:
        claims = jwt.get_unverified_claims(reset_token(w))
        if kind == "expired":
            claims["exp"] = datetime.utcnow() - timedelta(seconds=5)
        else:
            claims["pwd"] = "invalid"
        token = jwt.encode(claims, auth.settings.SECRET_KEY, algorithm=auth.settings.ALGORITHM)
    assert reset(w, token).status_code == 400
    with w.factory() as db:
        assert db.get(Utilisateur, 1).mot_de_passe == w.old_hash


def test_reset_token_cannot_authenticate_or_refresh(secured):
    w = secured
    token = reset_token(w)
    assert w.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert refresh(w, token).status_code == 401


def test_forgot_delivers_privately_and_does_not_enumerate(secured, caplog):
    w = secured
    existing = w.client.post("/api/v1/auth/forgot-password", json={"email": "a1@example.com"})
    missing = w.client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json() and set(existing.json()) == {"message"}
    assert len(w.sent) == 1 and w.sent[0][0] == "a1@example.com"
    token = parse_qs(urlparse(w.sent[0][1]).query)["token"][0]
    assert token not in existing.text and token not in caplog.text
    payload = security.decode_typed_token(token, "password_reset")
    assert w.old_hash not in str(payload)
    assert 3590 < payload["exp"] - time.time() <= 3600


def test_unconfigured_smtp_never_returns_a_token(secured, monkeypatch, caplog):
    monkeypatch.setattr(auth.EmailService, "is_configured", lambda: False)
    response = secured.client.post("/api/v1/auth/forgot-password", json={"email": "a1@example.com"})
    assert response.status_code == 200 and set(response.json()) == {"message"}
    assert not secured.sent and "SMTP" in caplog.text


def test_delivery_exception_does_not_log_token(secured, monkeypatch, caplog):
    def fail(email, link):
        raise RuntimeError("secret-link:" + link)
    monkeypatch.setattr(auth.EmailService, "send_password_reset_email", fail)
    assert secured.client.post("/api/v1/auth/forgot-password", json={"email": "a1@example.com"}).status_code == 200
    assert "secret-link:" not in caplog.text and "?token=" not in caplog.text


def test_success_consumes_reset_and_revokes_only_its_user(secured):
    w = secured
    own, other = pair(w), pair(w, 2)
    token = reset_token(w)
    verify = w.client.post("/api/v1/auth/verify-token", json={"token": token})
    assert verify.json() == {"valid": True, "user_id": 1}
    assert verify.headers["cache-control"] == "no-store"
    response = reset(w, token)
    assert response.status_code == 200
    with w.factory() as db:
        user = db.get(Utilisateur, 1)
        assert security.verify_password(NEW, user.mot_de_passe)
        assert not security.verify_password(OLD, user.mot_de_passe)
        assert not user.doit_changer_mot_de_passe
        assert user.mot_de_passe not in response.text
        assert db.get(Utilisateur, 2).mot_de_passe == w.old_hash
    assert reset(w, token).status_code == 400
    assert w.client.post("/api/v1/auth/verify-token", json={"token": token}).json() == {"valid": False}
    assert w.client.get("/api/v1/auth/me", headers=own.headers).status_code == 401
    assert refresh(w, own.refresh).status_code == 401
    assert w.client.get("/api/v1/auth/me", headers=other.headers).status_code == 200
    assert w.client.get("/api/v1/auth/verify-token/obsolete").status_code == 404


@pytest.mark.parametrize("stage", ["flush", "commit", "revocation"])
def test_reset_failure_rolls_back_hash_consumption_and_revocations(secured, monkeypatch, stage):
    w = secured
    own = pair(w)
    token = reset_token(w)
    invalidation = Mock()
    with monkeypatch.context() as m:
        m.setattr(auth, "invalidate_user_cache", invalidation)
        if stage == "revocation":
            m.setattr(SessionService, "revoke_sessions_in_transaction", Mock(side_effect=RuntimeError("failure")))
        else:
            m.setattr(Session, stage, Mock(side_effect=RuntimeError("failure")))
        assert reset(w, token).status_code == 500
    invalidation.assert_not_called()
    with w.factory() as db:
        assert db.get(Utilisateur, 1).mot_de_passe == w.old_hash
        assert SessionService.validate_session(db, own.sid, user_id=1)
    assert reset(w, token).status_code == 200  # Failed SQL transaction did not consume it.


def test_reset_cache_failure_is_not_a_failed_password_change(secured, monkeypatch):
    token = reset_token(secured)
    monkeypatch.setattr(auth, "invalidate_user_cache", Mock(side_effect=RuntimeError("cache failure")))
    assert reset(secured, token).status_code == 200
    assert reset(secured, token).status_code == 400


@pytest.mark.parametrize("endpoint", ["change-password", "force-change-password"])
def test_password_change_keeps_current_session_revokes_other_sessions(secured, endpoint):
    w = secured
    old_reset = reset_token(w)
    another = pair(w)
    assert change(w, endpoint).status_code == 200
    assert w.client.get("/api/v1/auth/me", headers=w.headers).status_code == 200
    assert w.client.get("/api/v1/auth/me", headers=another.headers).status_code == 401
    assert refresh(w, another.refresh).status_code == 401
    assert reset(w, old_reset).status_code == 400


@pytest.mark.parametrize("status,expected", [(True, 401), (None, 503)])
def test_blacklist_is_enforced_by_dependency(secured, monkeypatch, status, expected):
    monkeypatch.setattr(security.redis_client, "is_blacklisted", Mock(return_value=status))
    assert secured.client.get("/api/v1/auth/me", headers=secured.headers).status_code == expected
    assert refresh(secured, pair(secured).refresh).status_code == expected
    assert reset(secured, reset_token(secured)).status_code == expected


def test_real_redis_error_is_unknown_not_not_revoked(secured, monkeypatch):
    from app.core.redis_client import RedisClient
    monkeypatch.setattr(security.redis_client, "_get_client", lambda: Mock(exists=Mock(side_effect=RedisConnectionError("offline"))))
    # Call the real decorated implementation, bypassing the fixture's stub.
    assert RedisClient.is_blacklisted(security.redis_client, "test-jti") is None
    monkeypatch.setattr(security.redis_client, "_get_client", lambda: None)
    assert RedisClient.is_blacklisted(security.redis_client, "test-jti") is None


@pytest.mark.parametrize("cookie_only", [False, True])
def test_logout_revokes_exact_session_even_with_other_cookie(secured, cookie_only):
    w = secured
    own, other = pair(w), pair(w, 2)
    w.client.cookies.set(REFRESH_COOKIE, own.refresh if cookie_only else other.refresh)
    response = w.client.post("/api/v1/auth/logout", headers={} if cookie_only else own.headers)
    assert response.status_code == 200
    assert w.client.get("/api/v1/auth/me", headers=own.headers).status_code == 401
    assert w.client.get("/api/v1/auth/me", headers=other.headers).status_code == 200
    assert refresh(w, own.refresh).status_code == 401


def test_logout_succeeds_when_redis_fails_but_sql_revokes(secured, monkeypatch):
    w = secured
    own = pair(w)
    monkeypatch.setattr(security.redis_client, "revoke_session", Mock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(security.redis_client, "add_to_blacklist", Mock(return_value=False))
    assert w.client.post("/api/v1/auth/logout", headers=own.headers).status_code == 200
    assert w.client.get("/api/v1/auth/me", headers=own.headers).status_code == 401


def test_sql_revocation_overrides_old_redis_session(secured, monkeypatch):
    w = secured
    own = pair(w)
    monkeypatch.setattr(security.redis_client, "get_session", Mock(return_value={"revoked": False, "user_id": "1"}))
    with w.factory() as db:
        session = SessionService.get_session_by_uuid(db, own.sid, 1)
        assert inspect(session).persistent
        assert SessionService.revoke_session(db, own.sid, 1)
    with w.factory() as db:
        assert not SessionService.validate_session(db, own.sid, user_id=1)
        assert not SessionCacheService.is_session_active(db, 1, own.sid)
        assert not SessionCacheService.validate_session(db, 1, own.sid)[0]
    assert w.client.get("/api/v1/auth/me", headers=own.headers).status_code == 401


def test_refresh_rotation_checks_entire_token_and_prevents_replay(secured):
    w = secured
    own = pair(w)
    response = refresh(w, own.refresh)
    assert response.status_code == 200
    replacement = response.cookies.get(REFRESH_COOKIE)
    assert replacement != own.refresh
    assert not SessionService.verify_refresh_token(own.refresh, SessionService.hash_refresh_token(replacement))
    assert refresh(w, own.refresh).status_code == 401
    assert refresh(w, replacement).status_code == 200


def test_legacy_bcrypt_refresh_requires_login(secured):
    own = pair(secured)
    with secured.factory() as db:
        session = SessionService.get_session_by_uuid(db, own.sid)
        session.refresh_token_hash = security.get_password_hash(own.refresh[:72])
        db.commit()
    assert refresh(secured, own.refresh).status_code == 401


def test_refresh_commit_failure_leaves_old_token_valid(secured, monkeypatch):
    w = secured
    own = pair(w)
    with monkeypatch.context() as m:
        m.setattr(Session, "commit", Mock(side_effect=RuntimeError("failure")))
        assert refresh(w, own.refresh).status_code == 500
    assert refresh(w, own.refresh).status_code == 200


def test_login_and_tenant_isolation_with_real_sessions(secured):
    w = secured
    response = w.client.post("/api/v1/auth/login", json={"email": "a1@example.com", "mot_de_passe": OLD})
    assert response.status_code == 200, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert w.client.get("/api/v1/auth/me", headers=headers).status_code == 200
    w.client.app.include_router(utilisateurs.router, prefix="/api/v1")
    assert w.client.get("/api/v1/utilisateurs/2", headers=headers).status_code == 403
    assert w.client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert w.client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_middleware_does_not_exclude_every_path_or_trust_header_sid(secured, monkeypatch):
    w = secured
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")
    def database():
        with w.factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(session_middleware, "SessionLocal", w.factory)
    app.add_middleware(session_middleware.SessionValidationMiddleware)
    app.add_middleware(session_middleware.TokenValidationMiddleware)
    assert not session_middleware.SessionValidationMiddleware.is_excluded("/api/v1/auth/me")
    assert session_middleware.SessionValidationMiddleware.is_excluded("/api/v1/auth/token")
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/me", headers=w.headers).status_code == 200
        assert client.get("/api/v1/auth/me", headers={**w.headers, "X-Session-ID": "other"}).status_code == 401
        monkeypatch.setattr(security.redis_client, "is_blacklisted", Mock(return_value=None))
        assert client.get("/api/v1/auth/me", headers=w.headers).status_code == 503


def test_session_owner_must_match_signed_subject(secured):
    other = pair(secured, 2)
    token = security.create_access_token(1, session_uuid=other.sid)
    assert secured.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_logout_sql_failure_does_not_claim_success(secured, monkeypatch):
    own = pair(secured)
    blacklist = Mock()
    with monkeypatch.context() as m:
        m.setattr(Session, "commit", Mock(side_effect=RuntimeError("database failure")))
        m.setattr(security.redis_client, "add_to_blacklist", blacklist)
        assert secured.client.post("/api/v1/auth/logout", headers=own.headers).status_code == 500
    blacklist.assert_not_called()
    with secured.factory() as db:
        assert SessionService.validate_session(db, own.sid, user_id=1)


def test_session_service_bulk_revoke_is_atomic_and_preserves_exclusion(secured, monkeypatch):
    own, other = pair(secured), pair(secured)
    cache = Mock(return_value=True)
    monkeypatch.setattr(security.redis_client, "revoke_session", cache)
    with secured.factory() as db:
        with monkeypatch.context() as m:
            m.setattr(db, "commit", Mock(side_effect=RuntimeError("failure")))
            with pytest.raises(RuntimeError):
                SessionService.revoke_all_sessions(db, 1, exclude_uuid=own.sid)
    cache.assert_not_called()
    with secured.factory() as db:
        assert SessionService.validate_session(db, other.sid, user_id=1)
        assert SessionService.revoke_all_sessions(db, 1, exclude_uuid=own.sid) == 2
    assert all(call.args[1] != own.sid for call in cache.call_args_list)
    with secured.factory() as db:
        assert SessionCacheService.is_session_active(db, 1, own.sid)
        assert not SessionCacheService.is_session_active(db, 1, other.sid)


def test_optional_auth_does_not_swallow_revocation_outage(secured, monkeypatch):
    from app.api.dependencies import get_optional_user
    from fastapi import HTTPException
    monkeypatch.setattr(security.redis_client, "is_blacklisted", Mock(return_value=None))
    with secured.factory() as db:
        with pytest.raises(HTTPException) as exc:
            get_optional_user(None, db, secured.headers["Authorization"].split()[1])
        assert exc.value.status_code == 503


def test_smtp_exception_cannot_leak_message(secured, monkeypatch, caplog):
    from app.services import email_service
    monkeypatch.setattr(email_service.smtplib, "SMTP", Mock(side_effect=RuntimeError("private-reset-token")))
    assert send_reset_email("test@example.com", "https://example.com/private-reset-token") is False
    assert "private-reset-token" not in caplog.text


def test_admin_revokes_sessions_even_without_stored_access_jti(secured):
    from app.api.endpoints import admin_blacklist
    w = secured
    own = pair(w)
    w.client.app.include_router(admin_blacklist.router, prefix="/api/v1")
    response = w.client.post("/api/v1/admin/blacklist/user/1", headers=w.headers)
    assert response.status_code == 200, response.text
    assert response.json()["sessions_revoked"] == 2
    assert w.client.get("/api/v1/auth/me", headers=own.headers).status_code == 401


def test_admin_blacklist_retention_covers_token_lifetimes(secured):
    from app.api.endpoints import admin_blacklist
    w = secured
    w.client.app.include_router(admin_blacklist.router, prefix="/api/v1")
    response = w.client.post("/api/v1/admin/blacklist/token?jti=test-only&ttl=1", headers=w.headers)
    assert response.status_code == 200
    assert response.json()["ttl"] >= max(auth.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                                         auth.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, 3600)


def test_login_cache_exception_does_not_undo_session(secured, monkeypatch):
    monkeypatch.setattr(security.redis_client, "set_session", Mock(side_effect=RuntimeError("cache down")))
    response = secured.client.post("/api/v1/auth/login", json={"email": "a1@example.com", "mot_de_passe": OLD})
    assert response.status_code == 200
    with secured.factory() as db:
        assert SessionService.validate_session(db, response.json()["session_uuid"], user_id=1)


def test_session_activity_accepts_timezone_aware_timestamp(secured, monkeypatch):
    own = pair(secured)
    with secured.factory() as db:
        session = SessionService.get_session_by_uuid(db, own.sid)
        session.date_derniere_activite = datetime.now(timezone.utc) - timedelta(minutes=2)
        monkeypatch.setattr(SessionService, "get_session_by_uuid", lambda *args: session)
        monkeypatch.setattr(security.redis_client, "_client", Mock())
        assert SessionService.update_session_activity(db, own.sid)
