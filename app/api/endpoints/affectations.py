from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.dependencies import get_current_organisation_id
from app.core.dependencies_modules import require_module
from app.core.dependencies_permissions import require_permission
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.services import affectation_service

router = APIRouter(
    prefix="/affectations",
    tags=["Affectations"],
    dependencies=[Depends(require_module("MISSION"))],
)


class AffectationCreate(BaseModel):
    mission_id: int
    vehicule_id: int | None = None
    chauffeur_id: int | None = None
    date_debut: datetime
    date_fin: datetime
    statut: str = "PLANIFIEE"
    commentaire: str | None = None
    model_config = ConfigDict(extra="forbid")


@router.get("/", dependencies=[Depends(require_permission("MISSION_VOIR"))])
def list_affectations(
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    return affectation_service.list_affectations(db, organisation_id)


@router.post("/", status_code=201, dependencies=[Depends(require_permission("MISSION_AFFECTER"))])
def create_affectation(
    payload: AffectationCreate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        return affectation_service.create_affectation(db, payload.model_dump(), organisation_id)
    except affectation_service.AffectationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{affectation_id}", status_code=204,
               dependencies=[Depends(require_permission("MISSION_AFFECTER"))])
def delete_affectation(
    affectation_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    ok = affectation_service.delete_affectation(db, affectation_id, organisation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Affectation introuvable")