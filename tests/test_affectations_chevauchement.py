from datetime import date, datetime, timedelta

import pytest

from app.models.affectation_mission import AffectationMission
from app.models.chauffeur import Chauffeur
from app.models.maintenance import Maintenance
from app.models.mission import Mission
from app.models.vehicule import Vehicule
from app.services.affectation_service import AffectationConflict, create_affectation
from app.services.maintenance_service import MaintenanceService


def create_resources(db, organisation_id, vehicle_state="BON"):
    mission = Mission(organisation_id=organisation_id, description="Mission test")
    vehicule = Vehicule(
        organisation_id=organisation_id,
        id_localisation=organisation_id,
        numero_inventaire=f"INV-{organisation_id}-{vehicle_state}",
        id_type_bien=1,
        description="Test vehicle",
        immatriculation=f"PLATE-{organisation_id}-{vehicle_state}",
        etat=vehicle_state,
    )
    chauffeur = Chauffeur(
        organisation_id=organisation_id,
        nom="Test",
        prenom="Driver",
        numero_permis=f"PERMIS-{organisation_id}",
        date_expiration_permis=date(2028, 1, 1),
        actif=True,
    )
    db.add_all([mission, vehicule, chauffeur])
    db.commit()
    return mission, vehicule, chauffeur


def test_overlapping_vehicle_or_driver_assignments_are_rejected(flotte_db):
    with flotte_db() as db:
        mission, vehicule, chauffeur = create_resources(db, 1)
        start = datetime(2026, 9, 1, 8, 0)
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
        now = datetime(2026, 9, 1, 9, 0)
        with pytest.raises(ValueError, match="Véhicule introuvable"):
            create_affectation(db, {
                "mission_id": mission.id,
                "vehicule_id": foreign_vehicle.id_bien,
                "date_debut": now,
                "date_fin": now + timedelta(hours=1),
            }, 1)


def test_assignment_rejects_expired_license_or_inactive_driver(flotte_db):
    with flotte_db() as db:
        mission, vehicule, chauffeur = create_resources(db, 1)
        start = datetime(2026, 9, 1, 10, 0)
        end = start + timedelta(hours=3)

        # Chauffeur avec permis expiré
        chauffeur.date_expiration_permis = date(2026, 8, 31)
        db.commit()

        with pytest.raises(AffectationConflict, match="expiré"):
            create_affectation(db, {
                "mission_id": mission.id,
                "vehicule_id": vehicule.id_bien,
                "chauffeur_id": chauffeur.id,
                "date_debut": start,
                "date_fin": end,
            }, 1)

        # Rétablir permis valide mais désactiver le chauffeur
        chauffeur.date_expiration_permis = date(2030, 1, 1)
        chauffeur.actif = False
        db.commit()

        with pytest.raises(AffectationConflict, match="inactif"):
            create_affectation(db, {
                "mission_id": mission.id,
                "vehicule_id": vehicule.id_bien,
                "chauffeur_id": chauffeur.id,
                "date_debut": start,
                "date_fin": end,
            }, 1)


def test_assignment_rejects_unavailable_vehicle_state(flotte_db):
    with flotte_db() as db:
        mission, _, chauffeur = create_resources(db, 1)
        start = datetime(2026, 9, 2, 8, 0)
        end = start + timedelta(hours=4)

        for non_dispo_etat in ("PANNE", "MAINTENANCE", "REFORME"):
            _, v_ko, _ = create_resources(db, 1, vehicle_state=non_dispo_etat)
            with pytest.raises(AffectationConflict, match="non disponible"):
                create_affectation(db, {
                    "mission_id": mission.id,
                    "vehicule_id": v_ko.id_bien,
                    "chauffeur_id": chauffeur.id,
                    "date_debut": start,
                    "date_fin": end,
                }, 1)


def test_overlap_ignores_cancelled_or_rejected_assignments(flotte_db):
    with flotte_db() as db:
        mission, vehicule, chauffeur = create_resources(db, 1)
        start = datetime(2026, 9, 3, 8, 0)
        end = start + timedelta(hours=4)

        # Affectation existante mais ANNULEE
        aff_annulee = AffectationMission(
            organisation_id=1,
            mission_id=mission.id,
            vehicule_id=vehicule.id_bien,
            chauffeur_id=chauffeur.id,
            date_debut=start,
            date_fin=end,
            statut="ANNULEE",
        )
        db.add(aff_annulee)
        db.commit()

        # Nouvelle affectation sur EXACTEMENT la même période : doit être acceptée sans lever d'erreur
        nouvelle_aff = create_affectation(db, {
            "mission_id": mission.id,
            "vehicule_id": vehicule.id_bien,
            "chauffeur_id": chauffeur.id,
            "date_debut": start,
            "date_fin": end,
        }, 1)
        assert nouvelle_aff.id is not None
        assert nouvelle_aff.statut == "PLANIFIEE"


def test_bidirectional_conflict_with_maintenances(flotte_db):
    with flotte_db() as db:
        mission, vehicule, chauffeur = create_resources(db, 1)
        start = datetime.now() + timedelta(days=10)
        end = start + timedelta(hours=6)

        from app.models.maintenance import TypeMaintenance, StatutMaintenance
        from app.models.utilisateur import Utilisateur
        tech = db.query(Utilisateur).filter(Utilisateur.id == 1).first()
        if not tech:
            db.add(Utilisateur(id=1, organisation_id=1, email="tech1@org1.test", nom="Tech", prenom="Un", mot_de_passe="hash", role_id=1))
            db.commit()

        # 1. Maintenance active planifiée sur le véhicule
        maint = Maintenance(
            organisation_id=1,
            id_bien=vehicule.id_bien,
            id_technicien=1,
            type_maintenance=TypeMaintenance.PREVENTIVE,
            description="Révision",
            date_planifiee=start,
            statut=StatutMaintenance.PLANIFIEE,
        )
        db.add(maint)
        db.commit()

        # Tentative d'affectation mission sur la période -> refusée
        with pytest.raises(AffectationConflict, match="maintenance"):
            create_affectation(db, {
                "mission_id": mission.id,
                "vehicule_id": vehicule.id_bien,
                "chauffeur_id": chauffeur.id,
                "date_debut": start + timedelta(hours=1),
                "date_fin": end - timedelta(hours=1),
            }, 1)

        # Annuler la maintenance
        maint.statut = StatutMaintenance.ANNULEE
        db.commit()

        # Maintenant l'affectation mission passe
        aff = create_affectation(db, {
            "mission_id": mission.id,
            "vehicule_id": vehicule.id_bien,
            "chauffeur_id": chauffeur.id,
            "date_debut": start + timedelta(hours=1),
            "date_fin": end - timedelta(hours=1),
        }, 1)
        assert aff.id is not None

        # Et inversement : tentative de planifier une nouvelle maintenance chevauchant l'affectation active -> refusée
        from app.schemas.maintenance import MaintenanceCreate, TypeMaintenanceEnum
        maint_payload = MaintenanceCreate(
            id_bien=vehicule.id_bien,
            type_maintenance=TypeMaintenanceEnum.PREVENTIVE,
            date_planifiee=start + timedelta(hours=1),
            description="Maintenance urgente conflictuelle",
            periodicite_jours=1,
        )
        with pytest.raises(ValueError, match="Conflit de planning"):
            MaintenanceService(db).planifier_maintenance(maint_payload, id_technicien=1)