from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from ...core.database import get_db
from ...api.dependencies import get_current_organisation_id
from ...core.dependencies_modules import require_module
from ...core.dependencies_permissions import require_permission
from ...schemas.vehicule import VehiculeCreate, VehiculeRead, VehiculeUpdate
from ...services import vehicule_service
from ...services.organisation_service import OrganisationService
from ...services.vehicule_service import ImmatriculationConflict, VehiculeQuotaExceeded, VehiculeHasHistoryConflict

router = APIRouter(
    prefix="/vehicules",
    tags=["Véhicules"],
    dependencies=[Depends(require_module("VEHICULE"))],
)


@router.get("/", dependencies=[Depends(require_permission("VEHICULE_VOIR"))])
def get_vehicules(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    type_vehicule: Optional[str] = None,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    vehicules = vehicule_service.list_vehicules(
        db, organisation_id, skip, limit, type_vehicule
    )
    return {"total": len(vehicules), "vehicules": vehicules}


@router.get("/{bien_id}", response_model=VehiculeRead, dependencies=[Depends(require_permission("VEHICULE_VOIR"))])
def get_vehicule(
    bien_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    vehicule = vehicule_service.get_vehicule(db, bien_id, organisation_id)
    if not vehicule:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé")
    return vehicule


@router.post("/", response_model=VehiculeRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("VEHICULE_CREER"))])
def create_vehicule(
    payload: VehiculeCreate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    quota = OrganisationService(db).verifier_quota(organisation_id, "vehicules")
    if not quota["est_disponible"]:
        raise HTTPException(status_code=409, detail=quota["message"])
    try:
        return vehicule_service.create_vehicule(db, payload, organisation_id)
    except VehiculeQuotaExceeded as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ImmatriculationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflit lors de la création du véhicule")


@router.put("/{bien_id}", response_model=VehiculeRead,
            dependencies=[Depends(require_permission("VEHICULE_MODIFIER"))])
def update_vehicule(
    bien_id: int,
    payload: VehiculeUpdate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        vehicle = vehicule_service.update_vehicule(db, bien_id, payload, organisation_id)
    except ImmatriculationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflit lors de la modification du véhicule")
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé")
    return vehicle


@router.delete("/{bien_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_permission("VEHICULE_SUPPRIMER"))])
def delete_vehicule(
    bien_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        if not vehicule_service.delete_vehicule(db, bien_id, organisation_id):
            raise HTTPException(status_code=404, detail="Véhicule non trouvé")
    except VehiculeHasHistoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
