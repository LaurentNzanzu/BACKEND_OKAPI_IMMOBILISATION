from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.dependencies import get_current_organisation_id
from app.core.security import get_current_user
from app.core.dependencies_modules import require_module
from app.core.dependencies_permissions import require_permission
from app.models.utilisateur import Utilisateur
from app.schemas.mission import MissionCreate, MissionUpdate, MissionRead
from app.services import mission_service

router = APIRouter(
    prefix="/missions",
    tags=["Missions"],
    dependencies=[Depends(require_module("MISSION"))],
)


@router.get("/", response_model=list[MissionRead], dependencies=[Depends(require_permission("MISSION_VOIR"))])
def list_missions(
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    skip: int = 0,
    limit: int = Query(100, le=500),
):
    return mission_service.list_missions(db, organisation_id, skip, limit)


@router.get("/{mission_id}", response_model=MissionRead, dependencies=[Depends(require_permission("MISSION_VOIR"))])
def get_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    obj = mission_service.get_mission(db, mission_id, organisation_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return obj


@router.post("/", response_model=MissionRead, status_code=201,
             dependencies=[Depends(require_permission("MISSION_CREATE"))])
def create_mission(
    payload: MissionCreate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.create_mission(db, payload, organisation_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{mission_id}", response_model=MissionRead,
            dependencies=[Depends(require_permission("MISSION_MODIFIER"))])
def update_mission(
    mission_id: int,
    payload: MissionUpdate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        obj = mission_service.update_mission(db, mission_id, payload, organisation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not obj:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return obj


@router.delete("/{mission_id}", status_code=204,
               dependencies=[Depends(require_permission("MISSION_SUPPRIMER"))])
def delete_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    ok = mission_service.delete_mission(db, mission_id, organisation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mission introuvable")