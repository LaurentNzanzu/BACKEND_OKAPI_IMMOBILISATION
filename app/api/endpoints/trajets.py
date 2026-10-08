from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.dependencies import get_current_organisation_id
from app.core.dependencies_modules import require_module
from app.core.dependencies_permissions import require_permission
from app.schemas.trajet import TrajetCreate, TrajetUpdate, TrajetRead
from app.services import trajet_service

router = APIRouter(
    prefix="/trajets",
    tags=["Trajets"],
    dependencies=[Depends(require_module("TRAJET"))],
)


@router.get("", response_model=list[TrajetRead], dependencies=[Depends(require_permission("TRAJET_GERER"))], include_in_schema=False)
@router.get("/", response_model=list[TrajetRead], dependencies=[Depends(require_permission("TRAJET_GERER"))])
def list_trajets(
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    skip: int = 0,
    limit: int = Query(100, le=500),
):
    return trajet_service.list_trajets(db, organisation_id, skip, limit)


@router.get("/{trajet_id}", response_model=TrajetRead, dependencies=[Depends(require_permission("TRAJET_GERER"))])
def get_trajet(
    trajet_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    obj = trajet_service.get_trajet(db, trajet_id, organisation_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Trajet introuvable")
    return obj


@router.post("", response_model=TrajetRead, status_code=201,
             dependencies=[Depends(require_permission("TRAJET_GERER"))], include_in_schema=False)
@router.post("/", response_model=TrajetRead, status_code=201,
             dependencies=[Depends(require_permission("TRAJET_GERER"))])
def create_trajet(
    payload: TrajetCreate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        return trajet_service.create_trajet(db, payload, organisation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{trajet_id}", response_model=TrajetRead,
            dependencies=[Depends(require_permission("TRAJET_GERER"))])
def update_trajet(
    trajet_id: int,
    payload: TrajetUpdate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        obj = trajet_service.update_trajet(db, trajet_id, payload, organisation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not obj:
        raise HTTPException(status_code=404, detail="Trajet introuvable")
    return obj


@router.delete("/{trajet_id}", status_code=204,
               dependencies=[Depends(require_permission("TRAJET_GERER"))])
def delete_trajet(
    trajet_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    ok = trajet_service.delete_trajet(db, trajet_id, organisation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Trajet introuvable")