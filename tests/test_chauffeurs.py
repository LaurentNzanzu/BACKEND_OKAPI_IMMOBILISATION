from app.api.endpoints import chauffeurs
from app.models.chauffeur import Chauffeur
from flotte_test_support import flotte_client


def chauffeur_payload(numero_permis):
    return {"nom": "Doe", "prenom": "Jane", "numero_permis": numero_permis}


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