"""HTTP workflow tests with SQLite in memory; no application database is used."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Importing auth initializes Redis. Never contact external services in these tests.
with patch("redis.Redis.ping", return_value=True):
    from app.api.endpoints import utilisateurs, auth
from app.core.database import Base, get_db
from app.core.security import get_current_user, get_password_hash, verify_password
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.models.organisation import Organisation
from app.models.audit_log import AuditLog


@pytest.fixture
def workflow(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    names = ["organisations", "roles", "permissions", "role_permissions", "utilisateurs", "audit_logs"]
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in names])
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([Role(id_role=1, nom="ADMIN"), Role(id_role=2, nom="COMPTABLE")])
        db.add_all([Organisation(id=i, nom=f"ONG {i}", code=f"ONG{i}", email_admin=f"admin{i}@example.com") for i in (1, 2)])
        db.commit()
        initial_hash = get_password_hash("InitialPass9!")
        for uid, org, role in [(1, 1, 1), (2, 2, 1), (3, 1, 2), (4, None, 1)]:
            db.add(Utilisateur(id=uid, organisation_id=org, email=f"actor{uid}@example.com",
                nom="Admin", prenom="Test", role_id=role, mot_de_passe=initial_hash, est_actif=True))
        db.commit()
        app = FastAPI()
        app.include_router(utilisateurs.router, prefix="/api/v1")
        app.include_router(auth.router, prefix="/api/v1")
        def test_user(x_test_user: int = Header(default=1)):
            user = db.get(Utilisateur, x_test_user)
            if not user:
                raise HTTPException(status_code=401)
            return user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = test_user
        # Session infrastructure is tested separately; password checks and audit are real.
        monkeypatch.setattr(auth.SessionService, "create_session", lambda **kwargs: None)
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def payload(**changes):
    return dict(email="new@example.com", nom="Safari", prenom="Queen", post_nom="Test",
                telephone="+243970123456", role_id=2, **changes)


def create(client, **changes):
    data = payload()
    data.update(changes)
    return client.post("/api/v1/utilisateurs", json=data)


def test_creation_hash_tenant_audit_and_public_responses(workflow, caplog):
    client, db = workflow
    response = create(client, organisation_id=2, mot_de_passe="ClientPass9!")
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    temporary = data["mot_de_passe_temporaire"]
    assert data["doit_changer_mot_de_passe"] is True
    user = db.get(Utilisateur, data["id"])
    assert user.organisation_id == 1
    assert user.mot_de_passe != temporary
    assert verify_password(temporary, user.mot_de_passe)
    assert not verify_password("ClientPass9!", user.mot_de_passe)
    assert user.doit_changer_mot_de_passe is True
    assert len(temporary) == 12
    assert any(c.isupper() for c in temporary) and any(c.islower() for c in temporary)
    assert any(c.isdigit() for c in temporary) and any(not c.isalnum() for c in temporary)
    for url in [f"/api/v1/utilisateurs/{user.id}", "/api/v1/utilisateurs"]:
        public = client.get(url)
        assert public.status_code == 200
        assert "mot_de_passe" not in public.text
        assert temporary not in public.text
    audit = db.query(AuditLog).filter_by(action="CREATE", id_enregistrement=user.id).one()
    assert audit.id_utilisateur == 1
    assert audit.nouvelles_valeurs["organisation_id"] == 1
    assert "mot_de_passe" not in str(audit.nouvelles_valeurs)
    assert temporary not in caplog.text and user.mot_de_passe not in caplog.text


def test_creation_without_password_and_duplicate_email(workflow):
    client, _ = workflow
    assert create(client).status_code == 201
    assert create(client).status_code == 400


def test_role_and_authorization(workflow):
    client, _ = workflow
    assert create(client, role_id=999).status_code == 400
    assert client.post("/api/v1/utilisateurs", json=payload(), headers={"X-Test-User": "3"}).status_code == 403
    assert client.post("/api/v1/utilisateurs", json=payload(), headers={"X-Test-User": "999"}).status_code == 401


def test_existing_platform_behavior_preserved(workflow):
    client, db = workflow
    response = client.post("/api/v1/utilisateurs", json=payload(), headers={"X-Test-User": "4"})
    assert response.status_code == 201
    assert db.get(Utilisateur, response.json()["id"]).organisation_id is None


def test_login_and_existing_force_change(workflow):
    client, db = workflow
    created = create(client).json()
    temporary = created["mot_de_passe_temporaire"]
    def login(password):
        return client.post("/api/v1/auth/login", json={"email": created["email"], "mot_de_passe": password})
    response = login(temporary)
    assert response.status_code == 200
    assert response.json()["user"]["doit_changer_mot_de_passe"] is True
    assert "mot_de_passe_temporaire" not in response.text
    headers = {"X-Test-User": str(created["id"])}
    assert client.post("/api/v1/auth/force-change-password", json={"nouveau_mot_de_passe": "weak"}, headers=headers).status_code == 422
    response = client.post("/api/v1/auth/force-change-password", json={"nouveau_mot_de_passe": "PersonalPass9!"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["doit_changer_mot_de_passe"] is False
    user = db.get(Utilisateur, created["id"])
    assert verify_password("PersonalPass9!", user.mot_de_passe)
    assert not verify_password(temporary, user.mot_de_passe)
    assert login(temporary).status_code == 401
    assert login("PersonalPass9!").json()["user"]["doit_changer_mot_de_passe"] is False


@pytest.mark.parametrize("method,path,body", [
    ("get", "/2", None), ("put", "/2", {"nom": "Changed"}),
    ("delete", "/2", None), ("patch", "/2/toggle-actif", None),
])
def test_cross_tenant_denied(workflow, method, path, body):
    client, _ = workflow
    assert client.request(method, "/api/v1/utilisateurs" + path, json=body).status_code == 403
    assert 2 not in [u["id"] for u in client.get("/api/v1/utilisateurs").json()["items"]]


@pytest.mark.parametrize("phone", [None, "", "+243970123456", "+33612345678", "+123456789012345"])
def test_valid_phone(workflow, phone):
    client, _ = workflow
    assert create(client, telephone=phone).status_code == 201


@pytest.mark.parametrize("phone", ["970123456", "+243abc", "+243 970123456", "+012345678", "+1234567890123456", "+123"])
def test_invalid_phone(workflow, phone):
    client, _ = workflow
    assert create(client, telephone=phone).status_code == 422


def test_edit_preserves_password_and_toggle(workflow):
    client, db = workflow
    created = create(client).json()
    uid = created["id"]
    old_hash = db.get(Utilisateur, uid).mot_de_passe
    for fields in [{"nom": "Changed"}, {"mot_de_passe": "", "prenom": "Updated"}]:
        assert client.put(f"/api/v1/utilisateurs/{uid}", json=fields).status_code == 200
        assert db.get(Utilisateur, uid).mot_de_passe == old_hash
    assert client.patch(f"/api/v1/utilisateurs/{uid}/toggle-actif").json()["est_actif"] is False
    assert client.patch(f"/api/v1/utilisateurs/{uid}/toggle-actif").json()["est_actif"] is True


def test_optional_phone_can_be_cleared(workflow):
    client, db = workflow
    uid = create(client).json()["id"]
    assert client.put(f"/api/v1/utilisateurs/{uid}", json={"telephone": None}).status_code == 200
    assert db.get(Utilisateur, uid).telephone is None


def test_me_exposes_first_login_flag_without_credentials(workflow):
    client, _ = workflow
    created = create(client).json()
    login = client.post("/api/v1/auth/login", json={"email": created["email"], "mot_de_passe": created["mot_de_passe_temporaire"]}).json()
    response = client.get("/api/v1/auth/me", headers={"X-Test-User": str(created["id"]), "Authorization": "Bearer " + login["access_token"]})
    assert response.status_code == 200
    assert response.json()["doit_changer_mot_de_passe"] is True
    assert "mot_de_passe_temporaire" not in response.text
