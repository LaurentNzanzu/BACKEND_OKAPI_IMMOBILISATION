from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.validation import ValidationRequest, ValidationResponse
from ...services.validation_service import ValidationService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/validations", tags=["Validations"])

def check_validation_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]:
        return True
    if role in ["COMPTABLE", "CAISSE"] and action == "validate":
        return True
    if role in ["COMPTABLE", "CAISSE"] and action == "view":
        return True
    return False

@router.get("/en-attente", response_model=List[dict])
async def get_validations_en_attente(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    role = current_user.role.nom.upper() if current_user.role else "USER"
    return service.get_besoins_en_attente(role)

@router.post("/{besoin_id}/valider", response_model=dict)
async def valider_besoin(
    besoin_id: int,
    validation_data: ValidationRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    role = current_user.role.nom.upper() if current_user.role else "USER"
    
    try:
        besoin = service.valider_besoin(
            besoin_id=besoin_id,
            id_validateur=current_user.id,
            ordre_validateur=role,
            decision=validation_data.decision,
            commentaire=validation_data.commentaire
        )
        return {
            "success": True,
            "message": "Validation enregistrée",
            "besoin": besoin
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{besoin_id}/workflow")
async def get_workflow_validation(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    return service.get_workflow_details(besoin_id)

@router.get("/historique/{besoin_id}")
async def get_historique_validations(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    return service.get_historique_validations(besoin_id)