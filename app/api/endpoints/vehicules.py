from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from ...core.database import get_db
from ...api.dependencies import get_current_user, is_admin, require_any_roles, BIENS_VIEW_ROLES
from ...models.vehicule import Vehicule
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/vehicules", tags=["Véhicules"])


@router.get("/")
async def get_vehicules(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    type_vehicule: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_any_roles(BIENS_VIEW_ROLES)),
):
    query = db.query(Vehicule)
    if type_vehicule:
        query = query.filter(Vehicule.type_vehicule == type_vehicule)
    vehicules = query.offset(skip).limit(limit).all()
    return {"total": len(vehicules), "vehicules": vehicules}


@router.get("/{bien_id}")
async def get_vehicule(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_any_roles(BIENS_VIEW_ROLES)),
):
    vehicule = db.query(Vehicule).filter(Vehicule.id_bien == bien_id).first()
    if not vehicule:
        raise HTTPException(status_code=404, detail="Véhicule non trouvé")
    return vehicule
