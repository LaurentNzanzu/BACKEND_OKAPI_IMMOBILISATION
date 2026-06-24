from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.fourniture import (
    FournitureResponse,
    FournitureValiderRequest,
    FournitureRefuserRequest,
    FournitureStatistiques,
)
from ...services.fourniture_service import FournitureService
from ...services.audit_service import AuditService

router = APIRouter(prefix="/fournitures", tags=["Fournitures"])


def check_fourniture_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role == "ADMIN":
        return True
    if action == "view_en_attente" and role == "MAGASINIER":
        return True
    if action == "view_besoin" and role in ["TECHNICIEN", "MAGASINIER"]:
        return True
    if action == "valider" and role == "MAGASINIER":
        return True
    if action == "stats" and role in ["ADMIN", "GESTIONNAIRE"]:
        return True
    return False


@router.get("/en-attente", response_model=List[FournitureResponse])
async def get_fournitures_en_attente(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_fourniture_permission(current_user, "view_en_attente"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = FournitureService(db)
    role = current_user.role.nom.upper() if current_user.role else ""
    id_mag = current_user.id if role == "MAGASINIER" else None
    return service.get_fournitures_en_attente(id_magasinier=id_mag)


@router.get("/besoin/{besoin_id}", response_model=List[FournitureResponse])
async def get_fournitures_by_besoin(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_fourniture_permission(current_user, "view_besoin"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = FournitureService(db)
    return service.get_fournitures_by_besoin(besoin_id)


@router.post("/{id_fourniture}/valider", response_model=FournitureResponse)
async def valider_fourniture(
    id_fourniture: int,
    data: FournitureValiderRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not check_fourniture_permission(current_user, "valider"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = FournitureService(db)
    try:
        return service.valider_fourniture(
            id_fourniture=id_fourniture,
            quantite_fournie=data.quantite_fournie,
            id_magasinier=current_user.id,
            commentaire=data.commentaire,
            user_id_audit=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{id_fourniture}/refuser", response_model=FournitureResponse)
async def refuser_fourniture(
    id_fourniture: int,
    data: FournitureRefuserRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_fourniture_permission(current_user, "valider"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = FournitureService(db)
    try:
        return service.refuser_fourniture(
            id_fourniture=id_fourniture,
            id_magasinier=current_user.id,
            commentaire=data.commentaire,
            user_id_audit=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/statistiques", response_model=FournitureStatistiques)
async def get_fournitures_statistiques(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_fourniture_permission(current_user, "stats"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = FournitureService(db)
    return service.get_statistiques()
