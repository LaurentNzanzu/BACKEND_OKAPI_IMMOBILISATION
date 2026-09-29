from sqlalchemy.orm import Session
from app.models.trajet import Trajet
from app.models.mission import Mission
from app.models.mouvement_bien import MouvementBien
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.schemas.trajet import TrajetCreate, TrajetUpdate


def _verify_reference(db: Session, model, key, value, organisation_id: int, label: str):
    if value is None:
        return
    row = db.query(key).filter(
        key == value,
        model.organisation_id == organisation_id,
    ).first()
    if not row:
        raise ValueError(f"{label} introuvable dans cette organisation")


def _verify_references(db: Session, values: dict, organisation_id: int):
    _verify_reference(db, Mission, Mission.id, values.get("mission_id"), organisation_id, "Mission")
    _verify_reference(db, MouvementBien, MouvementBien.id_mouvement,
                      values.get("mouvement_bien_id"), organisation_id, "Mouvement")
    _verify_reference(db, Vehicule, Vehicule.id_bien, values.get("vehicule_id"), organisation_id, "Véhicule")
    _verify_reference(db, Chauffeur, Chauffeur.id, values.get("chauffeur_id"), organisation_id, "Chauffeur")


def list_trajets(db: Session, organisation_id: int, skip: int = 0, limit: int = 100):
    return (
        db.query(Trajet)
        .filter(Trajet.organisation_id == organisation_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_trajet(db: Session, trajet_id: int, organisation_id: int):
    return (
        db.query(Trajet)
        .filter(Trajet.id == trajet_id, Trajet.organisation_id == organisation_id)
        .first()
    )


def create_trajet(db: Session, data: TrajetCreate, organisation_id: int):
    try:
        values = data.model_dump()
        _verify_references(db, values, organisation_id)
        obj = Trajet(**values, organisation_id=organisation_id)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def update_trajet(db: Session, trajet_id: int, data: TrajetUpdate, organisation_id: int):
    try:
        obj = get_trajet(db, trajet_id, organisation_id)
        if not obj:
            return None
        changes = data.model_dump(exclude_unset=True)
        _verify_references(db, changes, organisation_id)
        for key, value in changes.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def delete_trajet(db: Session, trajet_id: int, organisation_id: int):
    obj = get_trajet(db, trajet_id, organisation_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True