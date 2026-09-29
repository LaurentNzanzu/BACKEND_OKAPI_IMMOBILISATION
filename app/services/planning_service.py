from datetime import datetime
from sqlalchemy.orm import Session
from app.models.affectation_mission import AffectationMission


def get_planning(
    db: Session,
    organisation_id: int,
    date_debut: datetime,
    date_fin: datetime,
):
    return (
        db.query(AffectationMission)
        .filter(
            AffectationMission.organisation_id == organisation_id,
            AffectationMission.date_debut < date_fin,
            AffectationMission.date_fin > date_debut,
        )
        .all()
    )