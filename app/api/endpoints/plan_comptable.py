# backend/app/api/endpoints/plan_comptable.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.plan_comptable import PlanComptable
from ...schemas.plan_comptable import PlanComptableCreate, PlanComptableUpdate, PlanComptableResponse

router = APIRouter(prefix="/plan-comptable", tags=["Plan Comptable"])

def check_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "COMPTABLE", "DG"]

@router.get("", response_model=List[PlanComptableResponse])
@router.get("/", response_model=List[PlanComptableResponse], include_in_schema=False)
async def get_plan_comptable(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    classe: Optional[str] = Query(None, description="Filtrer par classe"),
    type: Optional[str] = Query(None, description="Filtrer par type"),
    search: Optional[str] = Query(None, description="Recherche par numéro ou libellé"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(PlanComptable).filter(PlanComptable.est_actif == True)
    
    if classe:
        query = query.filter(PlanComptable.classe == classe)
    if type:
        query = query.filter(PlanComptable.type == type)
    if search:
        query = query.filter(
            (PlanComptable.numero.ilike(f"%{search}%")) |
            (PlanComptable.libelle.ilike(f"%{search}%"))
        )
    
    comptes = query.order_by(PlanComptable.numero).offset(skip).limit(limit).all()
    return comptes

@router.get("/{compte_id}", response_model=PlanComptableResponse)
async def get_compte_by_id(
    compte_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    compte = db.query(PlanComptable).filter(PlanComptable.id == compte_id).first()
    if not compte:
        raise HTTPException(status_code=404, detail="Compte non trouvé")
    return compte

@router.post("", response_model=PlanComptableResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=PlanComptableResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_compte(
    data: PlanComptableCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    existing = db.query(PlanComptable).filter(PlanComptable.numero == data.numero).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Le compte {data.numero} existe déjà")
    
    compte = PlanComptable(**data.model_dump())
    db.add(compte)
    db.commit()
    db.refresh(compte)
    return compte

@router.put("/{compte_id}", response_model=PlanComptableResponse)
async def update_compte(
    compte_id: int,
    data: PlanComptableUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    compte = db.query(PlanComptable).filter(PlanComptable.id == compte_id).first()
    if not compte:
        raise HTTPException(status_code=404, detail="Compte non trouvé")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(compte, key, value)
    
    db.commit()
    db.refresh(compte)
    return compte

@router.delete("/{compte_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_compte(
    compte_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    compte = db.query(PlanComptable).filter(PlanComptable.id == compte_id).first()
    if not compte:
        raise HTTPException(status_code=404, detail="Compte non trouvé")
    
    # Soft delete
    compte.est_actif = False
    db.commit()
    return None