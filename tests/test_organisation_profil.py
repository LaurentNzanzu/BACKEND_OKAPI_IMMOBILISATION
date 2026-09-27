"""Profile API tests: SQLite only, Cloudinary mocked, no production writes."""
import io
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
from PIL import Image
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.endpoints.organisation_profil import router
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models.organisation import Organisation
from app.models.role import Role
from app.models.utilisateur import Utilisateur
from app.models.audit_log import AuditLog
from app.services import organisation_profil_service as service


@pytest.fixture
def workflow(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    names = ["organisations", "roles", "permissions", "role_permissions", "utilisateurs", "audit_logs"]
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in names])
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([Role(id_role=1, nom="ADMIN"), Role(id_role=2, nom="COMPTABLE")])
        db.add_all([Organisation(id=i, nom=f"ONG {i}", code=f"ORG{i}", email_admin=f"admin{i}@example.com") for i in (1, 2)])
        db.commit()
        for uid, org, role in [(1, 1, 1), (2, 2, 1), (3, 1, 2), (4, None, 1)]:
            db.add(Utilisateur(id=uid, organisation_id=org, role_id=role, nom="Test", prenom="User",
                email=f"user{uid}@example.com", mot_de_passe="unused", est_actif=True))
        db.commit()
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        def user(x_test_user: int = Header(default=1)):
            return db.get(Utilisateur, x_test_user)
        app.dependency_overrides[get_current_user] = user
        app.dependency_overrides[get_db] = lambda: db
        upload = Mock(return_value={"secure_url": "https://res.cloudinary.com/test/image/upload/logo.png", "public_id": "new-logo"})
        destroy = Mock(return_value={"result": "ok"})
        monkeypatch.setattr(service.cloudinary.uploader, "upload", upload)
        monkeypatch.setattr(service.cloudinary.uploader, "destroy", destroy)
        with TestClient(app) as client:
            yield client, db, upload, destroy
    engine.dispose()


BASE = "/api/v1/organisations/me"


def png():
    stream = io.BytesIO()
    Image.new("RGB", (10, 10)).save(stream, format="PNG")
    return stream.getvalue()


def test_read_incomplete_and_isolated(workflow):
    client, _, _, _ = workflow
    for uid in (1, 2, 3):
        response = client.get(BASE + "/profil", headers={"X-Test-User": str(uid)})
        assert response.status_code == 200
        assert response.json()["id"] == (2 if uid == 2 else 1)
        assert response.json()["rccm"] is None
        assert "logo_public_id" not in response.json()
    assert client.get(BASE + "/profil", headers={"X-Test-User": "4"}).status_code == 403


def test_patch_partial_null_audit_and_admin_email(workflow):
    client, db, _, _ = workflow
    assert client.patch(BASE + "/profil", json={"rccm": "ABC", "ville": "Goma"}).status_code == 200
    response = client.patch(BASE + "/profil", json={"ville": "Bukavu", "email_contact": "contact@example.com"})
    assert response.json()["rccm"] == "ABC"
    assert response.json()["ville"] == "Bukavu"
    assert db.get(Organisation, 1).email_admin == "admin1@example.com"
    assert client.patch(BASE + "/profil", json={"rccm": None}).json()["rccm"] is None
    assert client.patch(BASE + "/profil", json={"ville": ""}).json()["ville"] is None
    assert db.query(AuditLog).count() == 4
    assert db.get(Organisation, 2).ville is None


@pytest.mark.parametrize("payload", [{"organisation_id": 2}, {"plan_abonnement": "PRO"}, {"logo_url": "https://example.com"}, {"nom": None}, {"nom": " "}, {"site_web": "javascript:alert(1)"}])
def test_forbidden_fields_and_invalid_name(workflow, payload):
    client, _, _, _ = workflow
    assert client.patch(BASE + "/profil", json=payload).status_code == 422


@pytest.mark.parametrize("uid", [3, 4])
def test_write_permissions(workflow, uid):
    client, _, upload, _ = workflow
    headers = {"X-Test-User": str(uid)}
    assert client.patch(BASE + "/profil", json={"nom": "Other"}, headers=headers).status_code == 403
    assert client.post(BASE + "/logo", files={"file": ("x.png", png())}, headers=headers).status_code == 403
    assert client.delete(BASE + "/logo", headers=headers).status_code == 403
    upload.assert_not_called()


def test_logo_upload_replace_delete(workflow):
    client, db, upload, destroy = workflow
    response = client.post(BASE + "/logo", files={"file": ("logo.png", png(), "image/png")})
    assert response.status_code == 200
    assert response.json()["logo_url"].startswith("https://")
    assert "logo_public_id" not in response.json()
    assert upload.call_args.kwargs["public_id"].startswith("organisations/1/logos/")
    assert db.get(Organisation, 2).logo_url is None
    upload.return_value = {"secure_url": "https://res.cloudinary.com/test/image/upload/next.png", "public_id": "next"}
    assert client.post(BASE + "/logo", files={"file": ("logo.png", png())}).status_code == 200
    assert destroy.call_args.args == ("new-logo",)
    assert client.delete(BASE + "/logo").json()["logo_url"] is None
    assert destroy.call_args.args == ("next",)
    assert client.delete(BASE + "/logo").status_code == 200


@pytest.mark.parametrize("content, status", [(b"not an image", 400), (b"x" * (2 * 1024 * 1024 + 1), 413)], ids=["invalid-format", "oversized"])
def test_invalid_logo(workflow, content, status):
    client, _, upload, _ = workflow
    assert client.post(BASE + "/logo", files={"file": ("logo.png", content, "image/png")}).status_code == status
    upload.assert_not_called()


def test_upload_failure_preserves_logo(workflow):
    client, db, upload, destroy = workflow
    org = db.get(Organisation, 1)
    org.logo_url, org.logo_public_id = "old-url", "old-id"
    db.commit()
    upload.side_effect = RuntimeError("unavailable")
    assert client.post(BASE + "/logo", files={"file": ("logo.png", png())}).status_code == 502
    assert db.get(Organisation, 1).logo_public_id == "old-id"
    destroy.assert_not_called()


def test_database_failure_cleans_new_logo_only(workflow, monkeypatch):
    client, db, _, destroy = workflow
    org = db.get(Organisation, 1)
    org.logo_url, org.logo_public_id = "old-url", "old-id"
    db.commit()
    monkeypatch.setattr(service.AuditService, "log_update", Mock(side_effect=RuntimeError("database unavailable")))
    response = client.post(BASE + "/logo", files={"file": ("logo.png", png())})
    assert response.status_code == 500
    assert response.json()["detail"] == "Impossible de mettre à jour le profil."
    assert db.get(Organisation, 1).logo_public_id == "old-id"
    assert destroy.call_args.args == ("new-logo",)


def test_document_owner_and_access_for_platform_and_tenants(workflow, monkeypatch):
    from datetime import date
    from app.models.bien import Bien
    from app.models.localisation import Localisation
    from app.services.etats_service import EtatsService
    from app.api.endpoints import etats
    from app.utils import etats_pdf_generator as pdf
    client, db, _, _ = workflow
    names = ["biens", "localisations", "composants", "maintenances", "pannes"]
    Base.metadata.create_all(db.bind, tables=[Base.metadata.tables[n] for n in names])
    db.add(Localisation(id_localisation=1, organisation_id=2, nom_localisation="BUREAU B"))
    db.add(Bien(id_bien=1, organisation_id=2, id_localisation=1, numero_inventaire="B-001",
                libelle="Bien B", date_acquisition=date(2024, 1, 1), prix_acquisition=100))
    org = db.get(Organisation, 2)
    org.logo_url = "https://example.com/B.png"
    db.commit()
    states = EtatsService(db)
    assert states.get_fiche_bien_data(1, organisation_id=1) is None
    data = states.get_fiche_bien_data(1, organisation_id=None)
    assert data["organisation"]["id"] == 2
    assert data["organisation"]["logo_url"].endswith("B.png")
    assert "logo_public_id" not in data["organisation"]
    client.app.include_router(etats.router, prefix="/api/v1")
    client.app.dependency_overrides[etats.router.dependencies[0].dependency] = lambda: None
    assert client.get("/api/v1/etats/fiche-bien/1?format=json").status_code == 404
    response = client.get("/api/v1/etats/fiche-bien/1?format=json", headers={"X-Test-User": "4"})
    assert response.status_code == 200
    assert response.json()["organisation"]["nom"] == "ONG 2"
    actual = pdf.add_organisation_header
    spy = Mock(wraps=actual)
    monkeypatch.setattr(pdf, "add_organisation_header", spy)
    result = pdf.generate_fiche_bien_pdf(data)
    assert result.startswith(b"%PDF")
    assert spy.call_args.args[2]["id"] == 2
    assert spy.call_args.args[2]["nom"] != "ONG 1"


def test_pdf_identity_escapes_text_and_omits_missing_fields(monkeypatch):
    from app.utils.organisation_pdf import add_organisation_header, logo_image
    from app.utils import organisation_pdf
    requests = Mock()
    monkeypatch.setattr(organisation_pdf.urllib3, "PoolManager", requests)
    assert logo_image("http://127.0.0.1/private") is None
    assert logo_image("https://res.cloudinary.com.evil.test/image.png") is None
    requests.assert_not_called()
    elements = []
    add_organisation_header(elements, 500, {"nom": "ONG <B> & fils"})
    assert elements[0].getPlainText() == "ONG <B> & fils"
    assert "RCCM" not in elements[0].getPlainText()


@pytest.mark.parametrize("format_name", ["PNG", "JPEG", "WEBP"])
def test_real_image_formats(format_name):
    stream = io.BytesIO()
    Image.new("RGB", (10, 10)).save(stream, format=format_name)
    service.OrganisationProfilService.validate_logo(stream.getvalue())


def test_gif_is_rejected():
    stream = io.BytesIO()
    Image.new("RGB", (10, 10)).save(stream, format="GIF")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        service.OrganisationProfilService.validate_logo(stream.getvalue())
    assert error.value.status_code == 400


def test_logo_pdf_load_and_unavailable_fallback(monkeypatch):
    from app.utils import organisation_pdf as pdf
    monkeypatch.setattr(pdf.settings, "CLOUDINARY_CLOUD_NAME", "test")
    response = Mock(status=200)
    response.stream.return_value = [png()]
    http = Mock()
    http.request.return_value = response
    manager = Mock()
    manager.__enter__ = Mock(return_value=http)
    manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(pdf.urllib3, "PoolManager", Mock(return_value=manager))
    assert pdf.logo_image("https://res.cloudinary.com/test/image/upload/logo.png") is not None
    assert http.request.call_args.kwargs["redirect"] is False
    response.close.assert_called_once()
    http.request.side_effect = TimeoutError()
    assert pdf.logo_image("https://res.cloudinary.com/test/image/upload/logo.png") is None
