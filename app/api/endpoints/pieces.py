# backend/app/api/endpoints/pieces.py
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.piece_rechange import PieceRechangeCreate, PieceRechangeUpdate, PieceRechangeResponse
from ...services.piece_service import PieceService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...api.dependencies import deny_comptable_pieces_access
from ...models.utilisateur import Utilisateur

router = APIRouter(
    prefix="/pieces-detachees",
    tags=["Pièces détachées"],
    dependencies=[Depends(deny_comptable_pieces_access)],
)

def check_piece_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG", "MAGASINIER"]:
        return True
    return action == "view"


@router.post("/", response_model=PieceRechangeResponse, status_code=status.HTTP_201_CREATED)
async def create_piece(
    data: PieceRechangeCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_piece_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = PieceService(db)
    audit_service = AuditService(db)
    
    piece = service.create_piece(data)
    
    # Enregistrer l'audit
    audit_service.log_create(
        user_id=current_user.id,
        table_name="pieces_rechange",
        record_id=piece.id_piece,
        new_values={
            "numero_serie": piece.numero_serie,
            "designation": piece.designation,
            "prix_achat": piece.prix_achat,
            "compatible_avec": piece.compatible_avec.value if piece.compatible_avec else None
        },
        request=request
    )
    
    return piece


@router.get("/recherche", response_model=PieceRechangeResponse)
async def rechercher_par_designation(
    q: str = Query(..., min_length=1, description="Désignation à rechercher"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_piece_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    if not q or len(q.strip()) < 1:
        raise HTTPException(status_code=400, detail="Le terme de recherche est requis")
    
    service = PieceService(db)
    piece = service.rechercher_par_designation(q.strip())
    
    if not piece:
        raise HTTPException(status_code=404, detail=f"Aucune pièce trouvée pour '{q}'")
    
    return piece


@router.get("/scan/{numero_serie}", response_model=PieceRechangeResponse)
async def rechercher_par_numero_serie(
    numero_serie: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_piece_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    if not numero_serie or len(numero_serie.strip()) < 1:
        raise HTTPException(status_code=400, detail="Le numéro de série est requis")
    
    service = PieceService(db)
    piece = service.rechercher_par_numero_serie(numero_serie.strip())
    
    if not piece:
        raise HTTPException(status_code=404, detail=f"Aucune pièce trouvée pour le numéro de série '{numero_serie}'")
    
    return piece


@router.get("/", response_model=List[PieceRechangeResponse])
async def get_pieces(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    est_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_piece_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PieceService(db)
    return service.get_all_pieces(skip, limit, est_active)


@router.get("/{piece_id}", response_model=PieceRechangeResponse)
async def get_piece(
    piece_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_piece_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PieceService(db)
    piece = service.get_piece(piece_id)
    if not piece:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    return piece


@router.put("/{piece_id}", response_model=PieceRechangeResponse)
async def update_piece(
    piece_id: int,
    data: PieceRechangeUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_piece_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = PieceService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancienne pièce
    old_piece = service.get_piece(piece_id)
    if not old_piece:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    
    piece = service.update_piece(piece_id, data)
    if not piece:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    
    # Enregistrer l'audit
    audit_service.log_update(
        user_id=current_user.id,
        table_name="pieces_rechange",
        record_id=piece_id,
        old_values={
            "designation": old_piece.designation,
            "prix_achat": old_piece.prix_achat,
            "stock_actuel": old_piece.stock_actuel,
            "stock_minimum": old_piece.stock_minimum
        },
        new_values={
            "designation": piece.designation,
            "prix_achat": piece.prix_achat,
            "stock_actuel": piece.stock_actuel,
            "stock_minimum": piece.stock_minimum
        },
        request=request
    )
    
    return piece


@router.delete("/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_piece(
    piece_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_piece_permission(current_user, "delete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = PieceService(db)
    audit_service = AuditService(db)
    
    # Récupérer la pièce avant suppression
    piece = service.get_piece(piece_id)
    if not piece:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    
    # Enregistrer l'audit
    audit_service.log_delete(
        user_id=current_user.id,
        table_name="pieces_rechange",
        record_id=piece_id,
        old_values={
            "numero_serie": piece.numero_serie,
            "designation": piece.designation
        },
        request=request
    )
    
    if not service.delete_piece(piece_id):
        raise HTTPException(status_code=404, detail="Pièce non trouvée")