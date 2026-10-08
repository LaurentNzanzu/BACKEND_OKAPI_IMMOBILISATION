from datetime import date, datetime, timedelta

from app.models.affectation_mission import AffectationMission
from app.models.mission import Mission
from app.models.vehicule import Vehicule
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


def test_delete_vehicle_without_history_is_allowed(flotte_db):
    with flotte_client(flotte_db, 1) as client:
        # Création d'un véhicule par erreur
        res_create = client.post("/api/v1/vehicules/", json=payload("DEL-001"))
        assert res_create.status_code == 201
        v_id = res_create.json()["id_bien"]

        # Suppression autorisée
        res_del = client.delete(f"/api/v1/vehicules/{v_id}")
        assert res_del.status_code == 204

        # Vérifier qu'il n'existe plus
        assert client.get(f"/api/v1/vehicules/{v_id}").status_code == 404


def test_delete_vehicle_with_history_rejected_409(flotte_db):
    with flotte_db() as db:
        vehicule = create_vehicule(db, VehiculeCreate(**payload("HIST-001", 1)), 1)
        v_id = vehicule.id_bien
        mission = Mission(organisation_id=1, description="Mission transport")
        db.add(mission)
        db.commit()

        # Ajouter une affectation historique
        aff = AffectationMission(
            organisation_id=1,
            mission_id=mission.id,
            vehicule_id=v_id,
            date_debut=datetime(2026, 8, 1, 8, 0),
            date_fin=datetime(2026, 8, 1, 12, 0),
            statut="TERMINEE",
        )
        db.add(aff)
        db.commit()

    with flotte_client(flotte_db, 1) as client:
        # Tentative de suppression -> 409 Conflict avec message de mise au rebut
        res_del = client.delete(f"/api/v1/vehicules/{v_id}")
        assert res_del.status_code == 409
        detail = res_del.json()["detail"]
        assert "historique" in detail.lower()
        assert "rebut" in detail.lower() or "reforme" in detail.lower()

        # Le véhicule doit toujours exister en base
        assert client.get(f"/api/v1/vehicules/{v_id}").status_code == 200