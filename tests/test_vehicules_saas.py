from datetime import date

from app.schemas.vehicule import VehiculeCreate
from app.services.vehicule_service import create_vehicule
from flotte_test_support import flotte_client


def payload(immatriculation="AA-001", organisation_id=1):
    return {
        "immatriculation": immatriculation,
        "libelle": "Pick-up",
        "id_localisation": organisation_id,
        "numero_inventaire": f"INV-{organisation_id}-{immatriculation}",
        "date_acquisition": date(2024, 1, 1).isoformat(),
        "marque": "Toyota",
    }


def test_tenant_cannot_list_or_read_other_organisations_vehicle(flotte_db):
    with flotte_db() as db:
        other = create_vehicule(db, VehiculeCreate(**payload("BB-002", 2)), 2)
        other_id = other.id_bien
    with flotte_client(flotte_db, 1) as client:
        response = client.get("/api/v1/vehicules/")
        assert response.status_code == 200
        assert response.json() == {"total": 0, "vehicules": []}
        assert client.get(f"/api/v1/vehicules/{other_id}").status_code == 404


def test_immatriculation_is_unique_per_organisation(flotte_db):
    with flotte_client(flotte_db, 1) as client:
        assert client.post("/api/v1/vehicules/", json=payload()).status_code == 201
        assert client.post("/api/v1/vehicules/", json=payload()).status_code == 409
    with flotte_client(flotte_db, 2) as client:
        response = client.post("/api/v1/vehicules/", json=payload("AA-001", 2))
        assert response.status_code == 201, response.text


def test_quota_blocks_vehicle_creation(flotte_db):
    with flotte_db() as db:
        db.get(__import__("app.models.organisation", fromlist=["Organisation"]).Organisation, 1).quota_vehicules = 0
        db.commit()
    with flotte_client(flotte_db, 1) as client:
        response = client.post("/api/v1/vehicules/", json=payload())
        assert response.status_code == 409


def test_disabled_vehicle_module_returns_forbidden(flotte_db):
    with flotte_db() as db:
        organisation = db.get(__import__("app.models.organisation", fromlist=["Organisation"]).Organisation, 1)
        organisation.parametres_json = {"modules_actifs": ["CHAUFFEUR"]}
        db.commit()
    with flotte_client(flotte_db, 1) as client:
        assert client.get("/api/v1/vehicules/").status_code == 403