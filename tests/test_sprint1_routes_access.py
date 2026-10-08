# tests/test_sprint1_routes_access.py
import pytest
from datetime import datetime
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import vehicules, chauffeurs, mission, affectations, trajets, planning
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.organisation import Organisation
from app.models.role import Role
from app.models.permission import Permission, role_permissions
from app.models.vehicule import Vehicule
from app.models.bien import Bien
from app.models.chauffeur import Chauffeur
from app.models.trajet import Trajet


def make_test_client(flotte_db, user_override=None):
    app = FastAPI()
    app.include_router(vehicules.router, prefix="/api/v1")
    app.include_router(chauffeurs.router, prefix="/api/v1")
    app.include_router(mission.router, prefix="/api/v1")
    app.include_router(affectations.router, prefix="/api/v1")
    app.include_router(trajets.router, prefix="/api/v1")
    app.include_router(planning.router, prefix="/api/v1")

    def override_db():
        with flotte_db() as db:
            yield db

    app.dependency_overrides[get_db] = override_db

    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override

    return TestClient(app)


def test_authorized_user_can_access_all_sprint1_routes(flotte_db):
    """
    1. Utilisateur autorisé (ADMIN ou profil habilité de l'organisation 1 avec tous modules actifs) :
       Reçoit 200 OK sur toutes les routes du Sprint 1.
    """
    user_admin = SimpleNamespace(
        id=1,
        organisation_id=1,
        email="admin@org1.test",
        role=SimpleNamespace(id_role=1, nom="ADMIN"),
    )
    client = make_test_client(flotte_db, user_override=user_admin)

    # 1. Véhicules
    r = client.get("/api/v1/vehicules/")
    assert r.status_code == 200, f"vehicules: {r.text}"

    # 2. Chauffeurs
    r = client.get("/api/v1/chauffeurs/")
    assert r.status_code == 200, f"chauffeurs: {r.text}"

    # 3. Missions
    r = client.get("/api/v1/missions/")
    assert r.status_code == 200, f"missions: {r.text}"

    # 4. Affectations
    r = client.get("/api/v1/affectations/")
    assert r.status_code == 200, f"affectations: {r.text}"

    # 5. Trajets
    r = client.get("/api/v1/trajets/")
    assert r.status_code == 200, f"trajets: {r.text}"

    # 6. Planning & Gantt
    r = client.get("/api/v1/planning/?date_debut=2026-01-01T00:00:00&date_fin=2026-01-31T23:59:59")
    assert r.status_code == 200, f"planning: {r.text}"

    r = client.get("/api/v1/planning/gantt?date_debut=2026-01-01T00:00:00&date_fin=2026-01-31T23:59:59")
    assert r.status_code == 200, f"planning gantt: {r.text}"
    assert "vehicules" in r.json()
    assert "affectations" in r.json()

    # 7. Chauffeurs disponibles
    r = client.get("/api/v1/chauffeurs/disponibles?date_debut=2026-01-01T00:00:00&date_fin=2026-01-02T00:00:00")
    assert r.status_code == 200, f"chauffeurs disponibles: {r.text}"


def test_user_without_organisation_gets_403_on_all_routes(flotte_db):
    """
    2a. Utilisateur sans organisation (organisation_id = None) :
        Reçoit 403 Forbidden sur toutes les routes nécessitant un tenant.
    """
    platform_user = SimpleNamespace(
        id=99,
        organisation_id=None,
        email="platform@okapi.test",
        role=SimpleNamespace(id_role=1, nom="ADMIN"),
    )
    client = make_test_client(flotte_db, user_override=platform_user)

    for path in ["/api/v1/vehicules/", "/api/v1/chauffeurs/", "/api/v1/missions/",
                 "/api/v1/affectations/", "/api/v1/trajets/"]:
        r = client.get(path)
        assert r.status_code == 403, f"Expected 403 for {path}, got {r.status_code}"
        assert "organisation est requise" in r.text.lower()


def test_user_with_missing_module_gets_403(flotte_db):
    """
    2b. Organisation dont le module n'est pas activé :
        Reçoit 403 Forbidden spécifiant que le module n'est pas activé.
    """
    # Créer une organisation 3 avec uniquement le module VEHICULE (sans TRAJET)
    with flotte_db() as db:
        db.add(Organisation(
            id=3,
            nom="Org Sans Trajet",
            code="ORG3",
            email_admin="admin3@test.org",
            statut="ACTIF",
            parametres_json={"modules_actifs": ["VEHICULE"]},
        ))
        db.commit()

    user_org3 = SimpleNamespace(
        id=30,
        organisation_id=3,
        email="user3@test.org",
        role=SimpleNamespace(id_role=1, nom="ADMIN"),
    )
    client = make_test_client(flotte_db, user_override=user_org3)

    # VEHICULE est actif -> 200
    r = client.get("/api/v1/vehicules/")
    assert r.status_code == 200

    # TRAJET n'est pas actif -> 403
    r = client.get("/api/v1/trajets/")
    assert r.status_code == 403
    assert "TRAJET" in r.text
    assert "pas activé" in r.text


def test_user_without_permission_gets_403(flotte_db):
    """
    2c. Rôle non-admin sans la permission granulaire requise :
        Reçoit 403 Forbidden ("Permission refusée").
    """
    with flotte_db() as db:
        # Créer un rôle 2 "VISITEUR" sans aucune permission attribuée
        role_visiteur = Role(id_role=2, nom="VISITEUR", description="Visiteur sans droits")
        db.add(role_visiteur)
        # Créer la permission en base pour que hasPermission ne bloque pas sur son inexistence
        perm = Permission(id_permission=10, nom="TRAJET_GERER", module="trajet", action="gerer", actif=True)
        db.add(perm)
        db.commit()

    user_visiteur = SimpleNamespace(
        id=40,
        organisation_id=1,
        email="visiteur@test.org",
        role=SimpleNamespace(id_role=2, nom="VISITEUR"),
    )
    client = make_test_client(flotte_db, user_override=user_visiteur)

    r = client.get("/api/v1/trajets/")
    assert r.status_code == 403
    assert "Permission refusée" in r.text or "trajet_gerer" in r.text.lower()


def test_tenant_isolation_no_data_leak_between_organisations(flotte_db):
    """
    3. Isolation multi-tenant :
       Un utilisateur de l'Organisation 2 ne peut voir aucune donnée créée dans l'Organisation 1.
    """
    with flotte_db() as db:
        from app.services.vehicule_service import create_vehicule
        from app.schemas.vehicule import VehiculeCreate
        payload_veh = {
            "immatriculation": "ORG1-IMMAT",
            "libelle": "Toyota Hilux Org 1",
            "id_localisation": 1,
            "numero_inventaire": "INV-ORG1-001",
            "date_acquisition": "2024-01-01",
            "marque": "Toyota",
        }
        create_vehicule(db, VehiculeCreate(**payload_veh), 1)
        db.add(Chauffeur(id=101, organisation_id=1, nom="Chauffeur Org1", prenom="Paul", numero_permis="P-ORG1"))
        db.add(Trajet(id=101, organisation_id=1, commentaire="Trajet Org 1"))
        db.commit()

    # Utilisateur Org 2
    user_org2 = SimpleNamespace(
        id=2,
        organisation_id=2,
        email="admin@org2.test",
        role=SimpleNamespace(id_role=1, nom="ADMIN"),
    )
    client_org2 = make_test_client(flotte_db, user_override=user_org2)

    # Org 2 consulte véhicules -> ne doit pas voir celui d'Org 1
    r_veh = client_org2.get("/api/v1/vehicules/")
    assert r_veh.status_code == 200
    assert r_veh.json()["total"] == 0
    assert r_veh.json()["vehicules"] == []

    # Org 2 consulte chauffeurs -> liste vide
    r_chauf = client_org2.get("/api/v1/chauffeurs/")
    assert r_chauf.status_code == 200
    assert len(r_chauf.json()) == 0

    # Org 2 consulte trajets -> liste vide
    r_traj = client_org2.get("/api/v1/trajets/")
    assert r_traj.status_code == 200
    assert len(r_traj.json()) == 0
