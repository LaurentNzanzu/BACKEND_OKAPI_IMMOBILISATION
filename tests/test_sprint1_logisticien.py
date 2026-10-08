# tests/test_sprint1_logisticien.py
import pytest
from datetime import datetime, date, timedelta
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import vehicules, chauffeurs, mission, affectations, trajets, planning
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.organisation import Organisation
from app.models.role import Role
from app.models.permission import Permission
from app.models.utilisateur import Utilisateur
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.models.mission import Mission
from app.models.audit_log import AuditLog
from app.schemas.vehicule import VehiculeCreate
from app.services.vehicule_service import create_vehicule
from app.services.mission_service import create_mission
from app.schemas.mission import MissionCreate


@pytest.fixture
def logisticien_env(flotte_db):
    """
    Configure les rôles LOGISTICIEN, RESPONSABLE_PROJET, CHAUFFEUR avec leurs permissions
    conformes au RBAC d'OKAPI Flotte.
    """
    with flotte_db() as db:
        # Permissions nécessaires
        perms_dict = {
            "MISSION_VOIR": Permission(id_permission=101, nom="MISSION_VOIR", module="mission", action="voir", actif=True),
            "MISSION_CREATE": Permission(id_permission=102, nom="MISSION_CREATE", module="mission", action="creer", actif=True),
            "MISSION_VALIDATE_LOG": Permission(id_permission=103, nom="MISSION_VALIDATE_LOG", module="mission", action="valider_log", actif=True),
            "MISSION_VALIDATE_DG": Permission(id_permission=104, nom="MISSION_VALIDATE_DG", module="mission", action="valider_dg", actif=True),
            "MISSION_AFFECTER": Permission(id_permission=105, nom="MISSION_AFFECTER", module="mission", action="affecter", actif=True),
            "MISSION_CLOSE": Permission(id_permission=106, nom="MISSION_CLOSE", module="mission", action="cloturer", actif=True),
            "MISSION_MODIFIER": Permission(id_permission=107, nom="MISSION_MODIFIER", module="mission", action="modifier", actif=True),
            "MISSION_SUPPRIMER": Permission(id_permission=108, nom="MISSION_SUPPRIMER", module="mission", action="supprimer", actif=True),
            "VEHICULE_VOIR": Permission(id_permission=109, nom="VEHICULE_VOIR", module="vehicule", action="voir", actif=True),
            "CHAUFFEUR_GERER": Permission(id_permission=110, nom="CHAUFFEUR_GERER", module="chauffeur", action="gerer", actif=True),
            "TRAJET_GERER": Permission(id_permission=111, nom="TRAJET_GERER", module="trajet", action="gerer", actif=True),
        }
        for p in perms_dict.values():
            db.merge(p)
        db.flush()

        # 1. Rôle LOGISTICIEN
        role_log = Role(id_role=8, nom="LOGISTICIEN", description="Logisticien de l'organisation")
        role_log.permissions = [
            perms_dict["MISSION_VOIR"],
            perms_dict["MISSION_VALIDATE_LOG"],
            perms_dict["MISSION_AFFECTER"],
            perms_dict["MISSION_CLOSE"],
            perms_dict["MISSION_MODIFIER"],
            perms_dict["MISSION_SUPPRIMER"],
            perms_dict["VEHICULE_VOIR"],
            perms_dict["CHAUFFEUR_GERER"],
            perms_dict["TRAJET_GERER"],
        ]
        db.merge(role_log)

        # 2. Rôle RESPONSABLE_PROJET
        role_rp = Role(id_role=9, nom="RESPONSABLE_PROJET", description="Chef de projet demandeur")
        role_rp.permissions = [
            perms_dict["MISSION_VOIR"],
            perms_dict["MISSION_CREATE"],
            perms_dict["MISSION_MODIFIER"],
        ]
        db.merge(role_rp)

        # 3. Rôle CHAUFFEUR
        role_ch = Role(id_role=10, nom="CHAUFFEUR", description="Conducteur")
        role_ch.permissions = [
            perms_dict["MISSION_VOIR"],
            perms_dict["TRAJET_GERER"],
        ]
        db.merge(role_ch)

        # Création des utilisateurs de test
        u_log = Utilisateur(
            id=80,
            organisation_id=1,
            email="logisticien@org1.test",
            nom="Log",
            prenom="Luc",
            mot_de_passe="hash",
            role_id=8,
            est_actif=True,
        )
        u_rp = Utilisateur(
            id=90,
            organisation_id=1,
            email="rp@org1.test",
            nom="Projet",
            prenom="Pierre",
            mot_de_passe="hash",
            role_id=9,
            est_actif=True,
        )
        u_ch = Utilisateur(
            id=100,
            organisation_id=1,
            email="chauffeur@org1.test",
            nom="Chauffeur",
            prenom="Charles",
            mot_de_passe="hash",
            role_id=10,
            est_actif=True,
        )
        # Logisticien Org 2
        u_log_org2 = Utilisateur(
            id=82,
            organisation_id=2,
            email="logisticien@org2.test",
            nom="Log2",
            prenom="Laurent",
            mot_de_passe="hash",
            role_id=8,
            est_actif=True,
        )
        for u in (u_log, u_rp, u_ch, u_log_org2):
            db.merge(u)

        # Véhicule & Chauffeur dans Org 1
        v1 = create_vehicule(
            db,
            VehiculeCreate(
                immatriculation="ORG1-LOG-01",
                libelle="Toyota Land Cruiser Org 1",
                id_localisation=1,
                numero_inventaire="INV-LOG-01",
                date_acquisition=date(2024, 1, 1),
                marque="Toyota",
                categorie="VOITURE",
                kilometrage_actuel=50000.0,
            ),
            organisation_id=1,
        )

        ch1 = Chauffeur(
            id=501,
            organisation_id=1,
            nom="Kabasele",
            prenom="Joseph",
            numero_permis="CD-LOG-01",
            categorie_permis="B",
            statut="DISPONIBLE",
            actif=True,
            disponible=True,
        )
        db.merge(ch1)

        # Véhicule & Chauffeur dans Org 2
        v2 = create_vehicule(
            db,
            VehiculeCreate(
                immatriculation="ORG2-LOG-02",
                libelle="Nissan Patrol Org 2",
                id_localisation=2,
                numero_inventaire="INV-LOG-02",
                date_acquisition=date(2024, 1, 1),
                marque="Nissan",
                categorie="VOITURE",
                kilometrage_actuel=30000.0,
            ),
            organisation_id=2,
        )
        ch2 = Chauffeur(
            id=502,
            organisation_id=2,
            nom="Tshisekedi",
            prenom="Alain",
            numero_permis="CD-LOG-02",
            categorie_permis="B",
            statut="DISPONIBLE",
            actif=True,
            disponible=True,
        )
        db.merge(ch2)
        db.commit()

    return {
        "vehicule_org1_id": v1.id_bien,
        "chauffeur_org1_id": 501,
        "vehicule_org2_id": v2.id_bien,
        "chauffeur_org2_id": 502,
    }


def make_client_for_user(flotte_db, user):
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
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_a_logisticien_full_lifecycle(flotte_db, logisticien_env):
    """
    Test a: L'utilisateur LOGISTICIEN peut lister les missions, valider une mission soumise,
    affecter un véhicule + chauffeur, démarrer la mission et la terminer.
    """
    with flotte_db() as db:
        role_log = db.get(Role, 8)
        u_log = db.get(Utilisateur, 80)
        # Attacher le rôle complet pour que role.permissions soit accessible
        user_log = SimpleNamespace(
            id=u_log.id,
            organisation_id=u_log.organisation_id,
            email=u_log.email,
            role=role_log,
        )

        # Créer une mission en attente de validation
        start = datetime(2026, 11, 1, 8, 0)
        end = start + timedelta(hours=8)
        m = Mission(
            organisation_id=1,
            numero_mission="MIS-TEST-001",
            description="Mission de terrain Kolwezi",
            lieu_arrivee="Kolwezi",
            date_debut=start,
            date_fin=end,
            statut="EN_ATTENTE_VALIDATION",
            cree_par=90,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mission_id = m.id

    client = make_client_for_user(flotte_db, user_log)

    # 1. Lister les missions (200 OK)
    r_list = client.get("/api/v1/missions/")
    assert r_list.status_code == 200
    assert any(item["id"] == mission_id for item in r_list.json())

    # 2. Valider la mission (200 OK -> VALIDEE)
    r_val = client.post(f"/api/v1/missions/{mission_id}/valider")
    assert r_val.status_code == 200
    assert r_val.json()["statut"] == "VALIDEE"

    # 3. Affecter véhicule + chauffeur (200 OK -> PLANIFIEE)
    r_aff = client.post(
        f"/api/v1/missions/{mission_id}/affecter",
        json={
            "vehicule_id": logisticien_env["vehicule_org1_id"],
            "chauffeur_id": logisticien_env["chauffeur_org1_id"],
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
            "commentaire": "Affectation par le logisticien",
        },
    )
    assert r_aff.status_code == 200, f"Affecter error: {r_aff.text}"

    # Vérifier statut mission passé à PLANIFIEE
    r_m = client.get(f"/api/v1/missions/{mission_id}")
    assert r_m.status_code == 200
    assert r_m.json()["statut"] == "PLANIFIEE"

    # 4. Démarrer la mission (200 OK -> EN_COURS)
    r_start = client.post(
        f"/api/v1/missions/{mission_id}/demarrer",
        json={
            "km_depart": 50000.0,
            "heure_depart": start.isoformat(),
        },
    )
    assert r_start.status_code == 200, f"Demarrer error: {r_start.text}"
    assert r_start.json()["statut"] == "EN_COURS"

    # 5. Terminer la mission (200 OK -> TERMINEE)
    r_end = client.post(
        f"/api/v1/missions/{mission_id}/terminer",
        json={
            "km_arrivee": 50150.0,
            "heure_retour": end.isoformat(),
            "observation": "Mission déroulée sans encombre",
        },
    )
    assert r_end.status_code == 200, f"Terminer error: {r_end.text}"
    assert r_end.json()["statut"] == "TERMINEE"


def test_b_unauthorized_roles_get_403(flotte_db, logisticien_env):
    """
    Test b:
    - RESPONSABLE_PROJET ne peut pas affecter (403)
    - CHAUFFEUR ne peut pas valider (403) ni affecter (403)
    - RESPONSABLE_PROJET ne peut pas valider (403)
    """
    with flotte_db() as db:
        role_rp = db.get(Role, 9)
        role_ch = db.get(Role, 10)
        u_rp = db.get(Utilisateur, 90)
        u_ch = db.get(Utilisateur, 100)

        user_rp = SimpleNamespace(
            id=u_rp.id,
            organisation_id=u_rp.organisation_id,
            email=u_rp.email,
            role=role_rp,
        )
        user_ch = SimpleNamespace(
            id=u_ch.id,
            organisation_id=u_ch.organisation_id,
            email=u_ch.email,
            role=role_ch,
        )

        # Créer une mission en attente de validation
        start = datetime(2026, 11, 2, 8, 0)
        end = start + timedelta(hours=6)
        m = Mission(
            organisation_id=1,
            numero_mission="MIS-TEST-002",
            description="Mission terrain Lubumbashi",
            lieu_arrivee="Lubumbashi",
            date_debut=start,
            date_fin=end,
            statut="EN_ATTENTE_VALIDATION",
            cree_par=90,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mission_id = m.id

    client_rp = make_client_for_user(flotte_db, user_rp)
    client_ch = make_client_for_user(flotte_db, user_ch)

    # 1. RESPONSABLE_PROJET tente d'affecter -> 403
    r1 = client_rp.post(
        f"/api/v1/missions/{mission_id}/affecter",
        json={
            "vehicule_id": logisticien_env["vehicule_org1_id"],
            "chauffeur_id": logisticien_env["chauffeur_org1_id"],
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
        },
    )
    assert r1.status_code == 403

    # 2. RESPONSABLE_PROJET tente de valider -> 403
    r2 = client_rp.post(f"/api/v1/missions/{mission_id}/valider")
    assert r2.status_code == 403

    # 3. CHAUFFEUR tente de valider -> 403
    r3 = client_ch.post(f"/api/v1/missions/{mission_id}/valider")
    assert r3.status_code == 403

    # 4. CHAUFFEUR tente d'affecter -> 403
    r4 = client_ch.post(
        f"/api/v1/missions/{mission_id}/affecter",
        json={
            "vehicule_id": logisticien_env["vehicule_org1_id"],
            "chauffeur_id": logisticien_env["chauffeur_org1_id"],
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
        },
    )
    assert r4.status_code == 403


def test_c_logisticien_cannot_create_mission(flotte_db, logisticien_env):
    """
    Test c: Le LOGISTICIEN n'a pas la permission MISSION_CREATE et reçoit un 403
    sur POST /missions/.
    """
    with flotte_db() as db:
        role_log = db.get(Role, 8)
        u_log = db.get(Utilisateur, 80)
        user_log = SimpleNamespace(
            id=u_log.id,
            organisation_id=u_log.organisation_id,
            email=u_log.email,
            role=role_log,
        )

    client = make_client_for_user(flotte_db, user_log)

    start = datetime(2026, 11, 3, 8, 0)
    end = start + timedelta(hours=5)
    r = client.post(
        "/api/v1/missions/",
        json={
            "description": "Mission tentée par le logisticien",
            "destination": "Likasi",
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
            "motif": "Supervision",
        },
    )
    assert r.status_code == 403, f"Expected 403 Forbidden, got {r.status_code}"


def test_d_logisticien_multi_tenant_isolation(flotte_db, logisticien_env):
    """
    Test d: Le LOGISTICIEN de l'Organisation 1 ne peut pas affecter un véhicule
    ou un chauffeur appartenant à l'Organisation 2.
    """
    with flotte_db() as db:
        role_log = db.get(Role, 8)
        u_log = db.get(Utilisateur, 80)
        user_log = SimpleNamespace(
            id=u_log.id,
            organisation_id=u_log.organisation_id,
            email=u_log.email,
            role=role_log,
        )

        start = datetime(2026, 11, 4, 8, 0)
        end = start + timedelta(hours=4)
        m = Mission(
            organisation_id=1,
            numero_mission="MIS-TEST-004",
            description="Mission Org 1",
            lieu_arrivee="Fungurume",
            date_debut=start,
            date_fin=end,
            statut="VALIDEE",
            cree_par=90,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mission_id = m.id

    client = make_client_for_user(flotte_db, user_log)

    # 1. Tentative avec véhicule de l'Org 2
    r_veh_org2 = client.post(
        f"/api/v1/missions/{mission_id}/affecter",
        json={
            "vehicule_id": logisticien_env["vehicule_org2_id"],
            "chauffeur_id": logisticien_env["chauffeur_org1_id"],
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
        },
    )
    assert r_veh_org2.status_code in (400, 404, 409), f"Expected 400/404/409, got {r_veh_org2.status_code}"

    # 2. Tentative avec chauffeur de l'Org 2
    r_ch_org2 = client.post(
        f"/api/v1/missions/{mission_id}/affecter",
        json={
            "vehicule_id": logisticien_env["vehicule_org1_id"],
            "chauffeur_id": logisticien_env["chauffeur_org2_id"],
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
        },
    )
    assert r_ch_org2.status_code in (400, 404, 409), f"Expected 400/404/409, got {r_ch_org2.status_code}"


def test_e_affectation_audit_log_traceability(flotte_db, logisticien_env):
    """
    Test e: Lors d'une affectation, une trace d'audit doit être enregistrée
    (table_concernee='affectations_mission', action='AFFECTATION_RESSOURCES').
    Ce test DOIT ÉCHOUER en Phase 0 tant que la traçabilité d'affectation
    n'est pas encore implémentée dans affectation_service.py (Phase 3).
    """
    with flotte_db() as db:
        role_log = db.get(Role, 8)
        u_log = db.get(Utilisateur, 80)
        user_log = SimpleNamespace(
            id=u_log.id,
            organisation_id=u_log.organisation_id,
            email=u_log.email,
            role=role_log,
        )

        start = datetime(2026, 11, 5, 8, 0)
        end = start + timedelta(hours=4)
        m = Mission(
            organisation_id=1,
            numero_mission="MIS-TEST-005",
            description="Mission pour test audit",
            lieu_arrivee="Kolwezi",
            date_debut=start,
            date_fin=end,
            statut="VALIDEE",
            cree_par=90,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mission_id = m.id

    client = make_client_for_user(flotte_db, user_log)

    r_aff = client.post(
        f"/api/v1/missions/{mission_id}/affecter",
        json={
            "vehicule_id": logisticien_env["vehicule_org1_id"],
            "chauffeur_id": logisticien_env["chauffeur_org1_id"],
            "date_debut": start.isoformat(),
            "date_fin": end.isoformat(),
            "commentaire": "Vérification audit",
        },
    )
    assert r_aff.status_code == 200

    # Vérification dans la table audit_logs
    with flotte_db() as db:
        logs = db.query(AuditLog).filter(
            AuditLog.table_concernee == "affectations_mission",
            AuditLog.action == "AFFECTATION_RESSOURCES",
        ).all()
        assert len(logs) >= 1, "Une entrée d'audit pour 'affectations_mission' / 'AFFECTATION_RESSOURCES' doit exister"
        log = logs[0]
        assert log.id_utilisateur == 80
        assert log.nouvelles_valeurs is not None
