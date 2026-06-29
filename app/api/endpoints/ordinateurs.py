from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from ...core.database import get_db
from ...api.dependencies import require_any_roles, BIENS_VIEW_ROLES
from ...models.ordinateur import Ordinateur
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/ordinateurs", tags=["Ordinateurs"])


@router.get("/")
async def get_ordinateurs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    marque: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_any_roles(BIENS_VIEW_ROLES)),
):
    query = db.query(Ordinateur)
    if marque:
        query = query.filter(Ordinateur.marque == marque)
    ordinateurs = query.offset(skip).limit(limit).all()
    return {"total": len(ordinateurs), "ordinateurs": ordinateurs}


@router.get("/{bien_id}")
async def get_ordinateur(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_any_roles(BIENS_VIEW_ROLES)),
):
    ordinateur = db.query(Ordinateur).filter(Ordinateur.id_bien == bien_id).first()
    if not ordinateur:
        raise HTTPException(status_code=404, detail="Ordinateur non trouvé")
    return ordinateur
