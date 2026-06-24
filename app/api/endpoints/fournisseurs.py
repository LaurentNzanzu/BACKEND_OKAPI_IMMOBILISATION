# backend/app/api/endpoints/fournisseurs.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.fournisseur import FournisseurCreate, FournisseurUpdate, FournisseurResponse
from ...services.fournisseur_service import FournisseurService

router = APIRouter(prefix="/fournisseurs", tags=["Fournisseurs"])


def check_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "COMPTABLE", "DG"]


@router.post("/", response_model=FournisseurResponse, status_code=status.HTTP_201_CREATED)
async def create_fournisseur(
    data: FournisseurCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = FournisseurService(db)
    return service.create(data)


@router.get("", response_model=List[FournisseurResponse])
@router.get("/", response_model=List[FournisseurResponse], include_in_schema=False)
async def get_fournisseurs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = FournisseurService(db)
    return service.get_all(skip=skip, limit=limit, search=search)


@router.get("/{fournisseur_id}", response_model=FournisseurResponse)
async def get_fournisseur(
    fournisseur_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = FournisseurService(db)
    fournisseur = service.get_by_id(fournisseur_id)
    if not fournisseur:
        raise HTTPException(status_code=404, detail="Fournisseur non trouvé")
    return fournisseur


@router.put("/{fournisseur_id}", response_model=FournisseurResponse)
async def update_fournisseur(
    fournisseur_id: int,
    data: FournisseurUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = FournisseurService(db)
    fournisseur = service.update(fournisseur_id, data)
    if not fournisseur:
        raise HTTPException(status_code=404, detail="Fournisseur non trouvé")
    return fournisseur


@router.delete("/{fournisseur_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fournisseur(
    fournisseur_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = FournisseurService(db)
    if not service.delete(fournisseur_id):
        raise HTTPException(status_code=404, detail="Fournisseur non trouvé")