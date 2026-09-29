from sqlalchemy.orm import Session
from app.models.chauffeur import Chauffeur
from app.schemas.chauffeur import ChauffeurCreate, ChauffeurUpdate
from app.services.organisation_service import OrganisationService


class ChauffeurQuotaExceeded(ValueError):
    pass


def list_chauffeurs(db: Session, organisation_id: int, skip: int = 0, limit: int = 100):
    return (
        db.query(Chauffeur)
        .filter(Chauffeur.organisation_id == organisation_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_chauffeur(db: Session, chauffeur_id: int, organisation_id: int):
    return (
        db.query(Chauffeur)
        .filter(Chauffeur.id == chauffeur_id, Chauffeur.organisation_id == organisation_id)
        .first()
    )


def create_chauffeur(db: Session, data: ChauffeurCreate, organisation_id: int):
    quota = OrganisationService(db).verifier_quota(organisation_id, "chauffeurs")
    if not quota["est_disponible"]:
        raise ChauffeurQuotaExceeded(quota["message"])
    try:
        obj = Chauffeur(**data.model_dump(), organisation_id=organisation_id)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def update_chauffeur(db: Session, chauffeur_id: int, data: ChauffeurUpdate, organisation_id: int):
    obj = get_chauffeur(db, chauffeur_id, organisation_id)
    if not obj:
        return None
    for key, value in data.dict(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete_chauffeur(db: Session, chauffeur_id: int, organisation_id: int):
    obj = get_chauffeur(db, chauffeur_id, organisation_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True