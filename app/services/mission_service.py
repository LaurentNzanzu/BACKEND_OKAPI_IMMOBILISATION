from sqlalchemy.orm import Session
from app.models.mission import Mission
from app.models.projet import Projet
from app.schemas.mission import MissionCreate, MissionUpdate


def list_missions(db: Session, organisation_id: int, skip: int = 0, limit: int = 100):
    return (
        db.query(Mission)
        .filter(Mission.organisation_id == organisation_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_mission(db: Session, mission_id: int, organisation_id: int):
    return (
        db.query(Mission)
        .filter(Mission.id == mission_id, Mission.organisation_id == organisation_id)
        .first()
    )


def _verify_project(db: Session, projet_id: int | None, organisation_id: int) -> None:
    if projet_id is None:
        return
    projet = db.query(Projet.id).filter(
        Projet.id == projet_id,
        Projet.organisation_id == organisation_id,
    ).first()
    if not projet:
        raise ValueError("Le projet est introuvable dans cette organisation")


def create_mission(db: Session, data: MissionCreate, organisation_id: int, user_id: int | None = None):
    try:
        values = data.model_dump()
        _verify_project(db, values.get("projet_id"), organisation_id)
        obj = Mission(**values, organisation_id=organisation_id, cree_par=user_id)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def update_mission(db: Session, mission_id: int, data: MissionUpdate, organisation_id: int):
    try:
        obj = get_mission(db, mission_id, organisation_id)
        if not obj:
            return None
        changes = data.model_dump(exclude_unset=True)
        if "projet_id" in changes:
            _verify_project(db, changes["projet_id"], organisation_id)
        for key, value in changes.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def delete_mission(db: Session, mission_id: int, organisation_id: int):
    obj = get_mission(db, mission_id, organisation_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True