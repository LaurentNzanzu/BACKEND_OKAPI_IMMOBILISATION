from datetime import datetime
from sqlalchemy.orm import Session
from app.models.affectation_mission import AffectationMission
from app.models.mission import Mission
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur


class AffectationConflict(ValueError):
    pass


def _has_overlap(
    db: Session,
    model,
    resource_field,
    resource_id: int,
    organisation_id: int,
    date_debut: datetime,
    date_fin: datetime,
    exclude_id: int | None = None,
):
    q = db.query(model).filter(
        model.organisation_id == organisation_id,
        resource_field == resource_id,
        model.date_debut < date_fin,
        model.date_fin > date_debut,
    )
    if exclude_id:
        q = q.filter(model.id != exclude_id)
    return q.first() is not None


def create_affectation(db: Session, data: dict, organisation_id: int):
    try:
        mission_id = data.get("mission_id")
        vehicule_id = data.get("vehicule_id")
        chauffeur_id = data.get("chauffeur_id")
        date_debut = data["date_debut"]
        date_fin = data["date_fin"]

        if date_debut >= date_fin:
            raise ValueError("date_debut doit être antérieure à date_fin")
        if not db.query(Mission.id).filter(
            Mission.id == mission_id, Mission.organisation_id == organisation_id
        ).with_for_update().first():
            raise ValueError("Mission introuvable dans cette organisation")
        if vehicule_id is not None and not db.query(Vehicule.id_bien).filter(
            Vehicule.id_bien == vehicule_id, Vehicule.organisation_id == organisation_id
        ).with_for_update().first():
            raise ValueError("Véhicule introuvable dans cette organisation")
        if chauffeur_id is not None and not db.query(Chauffeur.id).filter(
            Chauffeur.id == chauffeur_id, Chauffeur.organisation_id == organisation_id
        ).with_for_update().first():
            raise ValueError("Chauffeur introuvable dans cette organisation")

        if vehicule_id is not None and _has_overlap(
            db, AffectationMission, AffectationMission.vehicule_id,
            vehicule_id, organisation_id, date_debut, date_fin
        ):
            raise AffectationConflict("Véhicule déjà affecté sur cette période")
        if chauffeur_id is not None and _has_overlap(
            db, AffectationMission, AffectationMission.chauffeur_id,
            chauffeur_id, organisation_id, date_debut, date_fin
        ):
            raise AffectationConflict("Chauffeur déjà affecté sur cette période")

        allowed_fields = {
            "mission_id", "vehicule_id", "chauffeur_id", "date_debut", "date_fin",
            "statut", "commentaire",
        }
        obj = AffectationMission(
            **{key: value for key, value in data.items() if key in allowed_fields},
            organisation_id=organisation_id,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def list_affectations(db: Session, organisation_id: int):
    return (
        db.query(AffectationMission)
        .filter(AffectationMission.organisation_id == organisation_id)
        .all()
    )


def get_affectation(db: Session, affectation_id: int, organisation_id: int):
    return (
        db.query(AffectationMission)
        .filter(
            AffectationMission.id == affectation_id,
            AffectationMission.organisation_id == organisation_id,
        )
        .first()
    )


def delete_affectation(db: Session, affectation_id: int, organisation_id: int):
    obj = get_affectation(db, affectation_id, organisation_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True