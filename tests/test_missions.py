from datetime import date, datetime, timedelta
import pytest

from app.api.endpoints import mission as mission_ep
from app.models.mission import Mission
from app.models.organisation import Organisation
from app.models.projet import Projet
from app.schemas.mission import MissionCreate
from app.services.affectation_service import create_affectation
from app.services.mission_service import create_mission
from flotte_test_support import flotte_client


def _valid_payload(**kwargs):
    now = datetime(2026, 10, 10, 8, 0)
    data = {
        "description": "Mission humanitaire Nord-Kivu",
        "lieu_depart": "Goma",
        "lieu_arrivee": "Rutshuru",
        "date_debut": now,
        "date_fin": now + timedelta(days=2),
    }
    data.update(kwargs)
    return data


def test_mission_validation_rejects_empty_payload(flotte_db):
    with flotte_client(flotte_db, 1, mission_ep.router) as client:
        res = client.post("/api/v1/missions/", json={})
        assert res.status_code == 422


def test_mission_validation_rejects_inverted_dates(flotte_db):
    with flotte_client(flotte_db, 1, mission_ep.router) as client:
        now = datetime(2026, 10, 10, 8, 0)
        payload = {
            "description": "Mission dates invalides",
            "lieu_depart": "Goma",
            "lieu_arrivee": "Bukavu",
            "date_debut": (now + timedelta(days=2)).isoformat(),
            "date_fin": now.isoformat(),
        }
        res = client.post("/api/v1/missions/", json=payload)
        assert res.status_code == 422


def test_mission_auto_numbering(flotte_db):
    with flotte_db() as db:
        m1 = create_mission(db, MissionCreate(**_valid_payload(description="Mission 1")), organisation_id=1)
        m2 = create_mission(db, MissionCreate(**_valid_payload(description="Mission 2")), organisation_id=1)
        assert m1.numero_mission.startswith("MIS-")
        assert m2.numero_mission.startswith("MIS-")
        assert m1.numero_mission != m2.numero_mission


def test_mission_rejects_project_from_another_organisation(flotte_db):
    with flotte_db() as db:
        project = Projet(organisation_id=2, code="OTHER", nom="Other tenant")
        db.add(project)
        db.commit()
        project_id = project.id
        with pytest.raises(ValueError, match="cette organisation"):
            create_mission(db, MissionCreate(**_valid_payload(projet_id=project_id)), organisation_id=1)


def test_mission_without_project_is_allowed(flotte_db):
    with flotte_db() as db:
        mission = create_mission(db, MissionCreate(**_valid_payload()), organisation_id=1)
        assert mission.organisation_id == 1
        assert mission.projet_id is None
        assert mission.statut == "BROUILLON"


def test_mission_quota_blocks_creation(flotte_db):
    with flotte_db() as db:
        org = db.get(Organisation, 1)
        org.quota_missions_mois = 0
        db.commit()

    with flotte_client(flotte_db, 1, mission_ep.router) as client:
        payload = _valid_payload(description="Mission excédentaire")
        payload["date_debut"] = payload["date_debut"].isoformat()
        payload["date_fin"] = payload["date_fin"].isoformat()
        response = client.post("/api/v1/missions/", json=payload)
        assert response.status_code == 409
        assert "quota" in response.json()["detail"].lower()


def test_mission_workflow_lifecycle_submit_reject_and_affect(flotte_db):
    from app.models.workflow_etape import WorkflowEtape, TypeWorkflow
    with flotte_db() as db:
        db.add(WorkflowEtape(
            organisation_id=1,
            type_workflow=TypeWorkflow.MISSION,
            ordre=1,
            role_requis="ADMIN",
        ))
        db.commit()

    with flotte_client(flotte_db, 1, mission_ep.router) as client:
        # 1. Création en statut BROUILLON
        payload = _valid_payload(description="Mission vers site Nord")
        payload["date_debut"] = payload["date_debut"].isoformat()
        payload["date_fin"] = payload["date_fin"].isoformat()
        res1 = client.post("/api/v1/missions/", json=payload)
        assert res1.status_code == 201
        m_id = res1.json()["id"]
        assert res1.json()["statut"] == "BROUILLON"
        assert res1.json()["numero_mission"].startswith("MIS-")

        # 2. Soumission par l'utilisateur -> EN_ATTENTE_VALIDATION
        res_soumettre = client.post(f"/api/v1/missions/{m_id}/soumettre")
        assert res_soumettre.status_code == 200
        assert res_soumettre.json()["statut"] == "EN_ATTENTE_VALIDATION"

        # 3. Rejet de la mission avec un motif
        res_rejeter = client.post(f"/api/v1/missions/{m_id}/rejeter", json={"motif": "Budget carburant non disponible"})
        assert res_rejeter.status_code == 200
        assert res_rejeter.json()["statut"] == "REJETEE"
        assert res_rejeter.json()["motif_rejet"] == "Budget carburant non disponible"

        # 4. Modification possible après rejet
        res_edit = client.put(f"/api/v1/missions/{m_id}", json={"description": "Mission site Nord ajustée"})
        assert res_edit.status_code == 200

        # Re-soumission -> EN_ATTENTE_VALIDATION
        res_resubmit = client.post(f"/api/v1/missions/{m_id}/soumettre")
        assert res_resubmit.status_code == 200
        assert res_resubmit.json()["statut"] == "EN_ATTENTE_VALIDATION"

        # Validation de l'étape par l'ADMIN -> VALIDEE
        res_val = client.post(f"/api/v1/missions/{m_id}/valider")
        assert res_val.status_code == 200
        assert res_val.json()["statut"] == "VALIDEE"

    # 5. Affectation d'une ressource -> passage en PLANIFIEE
    with flotte_db() as db:
        start = datetime(2026, 9, 10, 8, 0)
        aff = create_affectation(db, {
            "mission_id": m_id,
            "date_debut": start,
            "date_fin": start + timedelta(hours=4),
        }, 1)
        assert aff.id is not None
        mission_obj = db.get(Mission, m_id)
        assert mission_obj.statut == "PLANIFIEE"


def test_mission_lifecycle_demarrer_terminer_with_odometer_and_trajet(flotte_db):
    from app.models.chauffeur import Chauffeur
    from app.models.trajet import Trajet
    from app.schemas.vehicule import VehiculeCreate
    from app.services.vehicule_service import create_vehicule
    from app.services.mission_service import demarrer_mission, terminer_mission, MissionWorkflowError

    with flotte_db() as db:
        chauffeur = Chauffeur(
            organisation_id=1,
            nom="Mukendi",
            prenom="Jean",
            telephone="+243810000001",
            numero_permis="CD-123456",
            categorie_permis="B",
            statut="DISPONIBLE",
            disponible=True,
            actif=True,
        )
        db.add(chauffeur)
        db.commit()
        db.refresh(chauffeur)

        vehicule = create_vehicule(
            db,
            VehiculeCreate(
                immatriculation="1234-AB-01",
                libelle="Toyota Hilux 4x4",
                id_localisation=1,
                numero_inventaire="INV-1-1234",
                date_acquisition=date(2024, 1, 1),
                marque="Toyota",
                categorie="VOITURE",
                kilometrage_actuel=15000.0,
            ),
            organisation_id=1,
        )

        start = datetime(2026, 10, 15, 8, 0)
        m = create_mission(
            db,
            MissionCreate(**_valid_payload(date_debut=start, date_fin=start + timedelta(days=1))),
            organisation_id=1,
        )
        m.statut = "VALIDEE"
        db.commit()

        create_affectation(
            db,
            {
                "mission_id": m.id,
                "chauffeur_id": chauffeur.id,
                "vehicule_id": vehicule.id_bien,
                "date_debut": start,
                "date_fin": start + timedelta(days=1),
            },
            1,
        )
        assert m.statut == "PLANIFIEE"

        t_dep = datetime(2026, 10, 15, 8, 30)
        demarrer_mission(db, m.id, km_depart=15000.0, heure_depart=t_dep, organisation_id=1)
        db.refresh(m)
        db.refresh(chauffeur)

        assert m.statut == "EN_COURS"
        assert m.km_depart == 15000.0
        assert m.heure_depart_reelle == t_dep
        assert chauffeur.statut == "EN_MISSION"
        assert chauffeur.disponible is False

        trajets = db.query(Trajet).filter(Trajet.mission_id == m.id).all()
        assert len(trajets) == 1
        assert trajets[0].statut == "EN_COURS"
        assert trajets[0].kilometrage_debut == 15000.0

        t_ret = datetime(2026, 10, 16, 17, 0)
        with pytest.raises(MissionWorkflowError):
            terminer_mission(db, m.id, km_arrivee=14900.0, heure_retour=t_ret, organisation_id=1)

        terminer_mission(db, m.id, km_arrivee=15280.0, heure_retour=t_ret, organisation_id=1, observation="RAS")
        db.refresh(m)
        db.refresh(chauffeur)
        db.refresh(vehicule)

        assert m.statut == "TERMINEE"
        assert m.km_arrivee == 15280.0
        assert chauffeur.statut == "DISPONIBLE"
        assert chauffeur.disponible is True
        assert vehicule.kilometrage_actuel == 15280.0

        trajet_clos = db.query(Trajet).filter(Trajet.mission_id == m.id).first()
        assert trajet_clos.statut == "TERMINE"
        assert trajet_clos.distance_km == 280.0


def test_mission_annuler_releases_chauffeur_and_trajets(flotte_db):
    from app.models.chauffeur import Chauffeur
    from app.models.trajet import Trajet
    from app.schemas.vehicule import VehiculeCreate
    from app.services.vehicule_service import create_vehicule
    from app.services.mission_service import demarrer_mission, annuler_mission, MissionWorkflowError

    with flotte_db() as db:
        chauffeur = Chauffeur(
            organisation_id=1,
            nom="Kabasele",
            prenom="Alain",
            telephone="+243810000002",
            numero_permis="CD-789012",
            categorie_permis="B",
            statut="DISPONIBLE",
            disponible=True,
            actif=True,
        )
        db.add(chauffeur)
        db.commit()
        db.refresh(chauffeur)

        vehicule = create_vehicule(
            db,
            VehiculeCreate(
                immatriculation="5678-CD-02",
                libelle="Toyota Prado",
                id_localisation=1,
                numero_inventaire="INV-1-5678",
                date_acquisition=date(2024, 1, 1),
                marque="Toyota",
                categorie="VOITURE",
                kilometrage_actuel=20000.0,
            ),
            organisation_id=1,
        )


        start = datetime(2026, 10, 20, 8, 0)
        m = create_mission(
            db,
            MissionCreate(**_valid_payload(date_debut=start, date_fin=start + timedelta(days=1))),
            organisation_id=1,
        )
        m.statut = "VALIDEE"
        db.commit()

        create_affectation(
            db,
            {
                "mission_id": m.id,
                "chauffeur_id": chauffeur.id,
                "vehicule_id": vehicule.id_bien,
                "date_debut": start,
                "date_fin": start + timedelta(days=1),
            },
            1,
        )

        demarrer_mission(db, m.id, km_depart=20000.0, heure_depart=start, organisation_id=1)
        db.refresh(chauffeur)
        assert chauffeur.statut == "EN_MISSION"

        annuler_mission(db, m.id, motif="Mission annulée par la sécurité", organisation_id=1)
        db.refresh(m)
        db.refresh(chauffeur)

        assert m.statut == "ANNULEE"
        assert chauffeur.statut == "DISPONIBLE"
        assert chauffeur.disponible is True

        trajet = db.query(Trajet).filter(Trajet.mission_id == m.id).first()
        assert trajet.statut == "ANOMALIE"

        m2 = create_mission(
            db,
            MissionCreate(**_valid_payload(date_debut=start, date_fin=start + timedelta(days=1))),
            organisation_id=1,
        )
        m2.statut = "TERMINEE"
        db.commit()
        with pytest.raises(MissionWorkflowError):
            annuler_mission(db, m2.id, motif="Test", organisation_id=1)