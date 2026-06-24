# backend/app/api/endpoints/pannes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.panne import PanneCreate, PanneUpdate, PanneResponse
from ...services.panne_service import PanneService
from ...services.bien_service import BienService
from ...core.bien_permissions import build_bien_context_dict
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.panne import StatutPanne

router = APIRouter(prefix="/pannes", tags=["Pannes"])

def check_panne_permission(user: Utilisateur, action: str) -> bool:
    if not user: 
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role == "ADMIN":
        return True
    if role == "DG" and action in ["view", "create", "update"]: 
        return True
    if role == "TECHNICIEN" and action in ["view", "create", "update"]: 
        return True
    if role == "COMPTABLE" and action == "view": 
        return True
    if role == "MAGASINIER" and action == "view":
        return True
    if role == "GESTIONNAIRE" and action == "view":
        return True
    if role == "CAISSE" and action == "view":
        return True
    return False


@router.post("/", response_model=PanneResponse, status_code=status.HTTP_201_CREATED)
async def declarer_panne(
    data: PanneCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_panne_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = PanneService(db)
    audit_service = AuditService(db)
    
    try:
        panne = service.declarer_panne(data, current_user.id)

        audit_service.log_create(
            user_id=current_user.id,
            table_name="pannes",
            record_id=panne.id_panne,
            new_values={
                "id_bien": data.id_bien,
                "type_panne": data.type_panne.value if hasattr(data.type_panne, 'value') else str(data.type_panne),
                "description": data.description,
                "statut": panne.statut.value if panne.statut else None
            },
            request=request
        )
        
        return panne
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bien/{bien_id}", response_model=List[PanneResponse])
async def get_pannes_by_bien(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    return service.get_pannes_by_bien(bien_id)


@router.get("/mes-pannes", response_model=List[PanneResponse])
async def get_mes_pannes(
    statut: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    if current_user.role.nom.upper() == "TECHNICIEN":
        return service.get_pannes_by_technicien(current_user.id, statut)
    return service.get_pannes_actives()


@router.get("/actives", response_model=List[PanneResponse])
async def get_pannes_actives(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    return service.get_pannes_actives()


@router.get("/{panne_id}", response_model=PanneResponse)
async def get_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    panne = service.get_panne(panne_id)
    if not panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    bien_service = BienService(db)
    bien = bien_service.get_bien_by_id(panne.id_bien)
    response = PanneResponse.model_validate(panne)
    if bien:
        response.bien_context = build_bien_context_dict(bien, current_user)
    return response


@router.put("/{panne_id}", response_model=PanneResponse)
async def update_panne(
    panne_id: int,
    data: PanneUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_panne_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = PanneService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancienne panne
    old_panne = service.get_panne(panne_id)
    if not old_panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")
    
    panne = service.update_panne(panne_id, data)
    if not panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")
    
    # Enregistrer l'audit
    audit_service.log_update(
        user_id=current_user.id,
        table_name="pannes",
        record_id=panne_id,
        old_values={
            "statut": old_panne.statut.value if old_panne.statut else None,
            "description": old_panne.description
        },
        new_values={
            "statut": panne.statut.value if panne.statut else None,
            "description": panne.description
        },
        request=request
    )
    
    return panne


@router.patch("/{panne_id}/statut", response_model=PanneResponse)
async def changer_statut_panne(
    panne_id: int,
    statut: StatutPanne,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_panne_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = PanneService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancien statut
    old_panne = service.get_panne(panne_id)
    if not old_panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")
    
    panne = service.changer_statut(panne_id, statut)
    if not panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")
    
    # Enregistrer l'audit
    audit_service.log_update(
        user_id=current_user.id,
        table_name="pannes",
        record_id=panne_id,
        old_values={"statut": old_panne.statut.value if old_panne.statut else None},
        new_values={"statut": statut.value},
        request=request
    )
    
    return panne


@router.post("/{panne_id}/resoudre", response_model=PanneResponse)
async def resoudre_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not check_panne_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    if current_user.role.nom.upper() != "TECHNICIEN":
        raise HTTPException(status_code=403, detail="Seul un technicien peut résoudre une panne")

    service = PanneService(db)
    try:
        return service.resoudre_panne(panne_id, current_user.id)
    except ValueError as e:
        if "non trouvée" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/statistiques/summary")
async def get_pannes_statistiques(
    bien_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    return service.get_statistiques(bien_id)