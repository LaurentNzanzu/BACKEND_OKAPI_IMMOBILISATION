from datetime import datetime, timedelta
from app.api.endpoints import chauffeurs
from app.models.affectation_mission import AffectationMission
from app.models.chauffeur import Chauffeur
from app.models.mission import Mission
from flotte_test_support import flotte_client


def chauffeur_payload(numero_permis, utilisateur_id=None):
    payload = {"nom": "Doe", "prenom": "Jane", "numero_permis": numero_permis}
    if utilisateur_id is not None:
        payload["utilisateur_id"] = utilisateur_id
    return payload


def test_chauffeur_list_is_tenant_scoped(flotte_db):
    with flotte_db() as db:
        db.add(Chauffeur(organisation_id=2, nom="Other", prenom="Tenant", numero_permis="PERMIS-B"))
        db.commit()
    with flotte_client(flotte_db, 1, chauffeurs.router) as client:
        response = client.get("/api/v1/chauffeurs/")
        assert response.status_code == 200
        assert response.json() == []


def test_chauffeur_quota_blocks_creation(flotte_db):
    with flotte_db() as db:
        db.get(__import__("app.models.organisation", fromlist=["Organisation"]).Organisation, 1).quota_chauffeurs = 0
        db.commit()
    with flotte_client(flotte_db, 1, chauffeurs.router) as client:
        response = client.post("/api/v1/chauffeurs/", json=chauffeur_payload("PERMIS-A"))
        assert response.status_code == 409


def test_chauffeur_without_user_allowed_and_multiple_nulls(flotte_db):
    with flotte_client(flotte_db, 1, chauffeurs.router) as client:
        res1 = client.post("/api/v1/chauffeurs/", json=chauffeur_payload("PERMIS-NULL-1"))
        assert res1.status_code == 201
        assert res1.json()["utilisateur_id"] is None

        res2 = client.post("/api/v1/chauffeurs/", json=chauffeur_payload("PERMIS-NULL-2"))
        assert res2.status_code == 201
        assert res2.json()["utilisateur_id"] is None


def test_chauffeur_unique_active_user_per_tenant(flotte_db):
    from app.models.utilisateur import Utilisateur
    with flotte_db() as db:
        db.add_all([
            Utilisateur(id=10, organisation_id=1, email="u10@org1.test", nom="U10", prenom="P10", mot_de_passe="hash", role_id=1),
            Utilisateur(id=20, organisation_id=2, email="u20@org2.test", nom="U20", prenom="P20", mot_de_passe="hash", role_id=1),
        ])
        db.commit()

    with flotte_client(flotte_db, 1, chauffeurs.router) as client1:
        res1 = client1.post("/api/v1/chauffeurs/", json=chauffeur_payload("PERMIS-U1", utilisateur_id=10))
        assert res1.status_code == 201

        # Même organisation, même utilisateur_id -> Conflit 409
        res2 = client1.post("/api/v1/chauffeurs/", json=chauffeur_payload("PERMIS-U2", utilisateur_id=10))
        assert res2.status_code == 409

    # Organisation 2 différente avec son propre utilisateur -> Autorisé
    with flotte_client(flotte_db, 2, chauffeurs.router) as client2:
        res3 = client2.post("/api/v1/chauffeurs/", json=chauffeur_payload("PERMIS-U3", utilisateur_id=20))
        assert res3.status_code == 201


def test_chauffeur_delete_smart_soft_delete_with_history(flotte_db):
    with flotte_db() as db:
        ch_sans_hist = Chauffeur(organisation_id=1, nom="Sans", prenom="Hist", numero_permis="PERM-SANS")
        ch_avec_hist = Chauffeur(organisation_id=1, nom="Avec", prenom="Hist", numero_permis="PERM-AVEC")
        mission = Mission(organisation_id=1, description="Mission test")
        db.add_all([ch_sans_hist, ch_avec_hist, mission])
        db.commit()

        start = datetime(2026, 9, 1, 8, 0)
        aff = AffectationMission(
            organisation_id=1,
            mission_id=mission.id,
            chauffeur_id=ch_avec_hist.id,
            date_debut=start,
            date_fin=start + timedelta(hours=4),
        )
        db.add(aff)
        db.commit()
        id_sans = ch_sans_hist.id
        id_avec = ch_avec_hist.id

    with flotte_client(flotte_db, 1, chauffeurs.router) as client:
        # Suppression sans historique -> hard delete
        del1 = client.delete(f"/api/v1/chauffeurs/{id_sans}")
        assert del1.status_code == 204
        with flotte_db() as db:
            assert db.query(Chauffeur).filter(Chauffeur.id == id_sans).first() is None

        # Suppression avec historique -> soft delete (actif=False, disponible=False)
        del2 = client.delete(f"/api/v1/chauffeurs/{id_avec}")
        assert del2.status_code == 204
        with flotte_db() as db:
            ch_preserved = db.query(Chauffeur).filter(Chauffeur.id == id_avec).first()
            assert ch_preserved is not None
            assert ch_preserved.actif is False
            assert ch_preserved.disponible is False


def test_chauffeur_validation_rejects_invalid_status():
    import pytest
    from app.schemas.chauffeur import ChauffeurCreate
    with pytest.raises(ValueError, match="Statut invalide"):
        ChauffeurCreate(nom="Test", prenom="User", numero_permis="P-123", statut="STATUT_INCONNU")