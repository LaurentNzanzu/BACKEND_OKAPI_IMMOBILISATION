from datetime import datetime, timedelta

import pytest

from app.models.chauffeur import Chauffeur
from app.models.mission import Mission
from app.models.vehicule import Vehicule
from app.services.affectation_service import AffectationConflict, create_affectation
def create_resources(db, organisation_id):
    mission = Mission(organisation_id=organisation_id)
    vehicule = Vehicule(
        organisation_id=organisation_id,
        id_localisation=organisation_id,
        numero_inventaire=f"INV-{organisation_id}",
        id_type_bien=1,
        description="Test vehicle",
        immatriculation=f"PLATE-{organisation_id}",
    )
    chauffeur = Chauffeur(
        organisation_id=organisation_id,
        nom="Test",
        prenom="Driver",
        numero_permis=f"PERMIS-{organisation_id}",
    )
    db.add_all([mission, vehicule, chauffeur])
    db.commit()
    return mission, vehicule, chauffeur


def test_overlapping_vehicle_or_driver_assignments_are_rejected(flotte_db):
    with flotte_db() as db:
        mission, vehicule, chauffeur = create_resources(db, 1)
        start = datetime(2026, 9, 1)
        end = start + timedelta(hours=2)
        base = {
            "mission_id": mission.id,
            "vehicule_id": vehicule.id_bien,
            "chauffeur_id": chauffeur.id,
            "date_debut": start,
            "date_fin": end,
        }
        create_affectation(db, base, 1)
        for changed in ("vehicule_id", "chauffeur_id"):
            values = dict(base, mission_id=mission.id, date_debut=start + timedelta(minutes=30),
                          date_fin=end + timedelta(minutes=30))
            if changed == "vehicule_id":
                values["chauffeur_id"] = None
            else:
                values["vehicule_id"] = None
            with pytest.raises(AffectationConflict):
                create_affectation(db, values, 1)


def test_assignment_rejects_resource_from_another_organisation(flotte_db):
    with flotte_db() as db:
        mission, _, _ = create_resources(db, 1)
        _, foreign_vehicle, _ = create_resources(db, 2)
        now = datetime(2026, 9, 1)
        with pytest.raises(ValueError, match="Véhicule introuvable"):
            create_affectation(db, {
                "mission_id": mission.id,
                "vehicule_id": foreign_vehicle.id_bien,
                "date_debut": now,
                "date_fin": now + timedelta(hours=1),
            }, 1)