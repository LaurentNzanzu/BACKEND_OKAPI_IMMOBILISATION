from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.besoin import BesoinCreate, BesoinUpdate, BesoinResponse, AjoutLigneRequest
from ...services.besoin_service import BesoinService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.besoin import Besoin

router = APIRouter(prefix="/besoins", tags=["Besoins"])

def check_besoin_permission(user: Utilisateur, action: str) -> bool:
    if not user: 
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN"]: 
        return True
    if action == "view": 
        return True
    if action == "create" and role in ["TECHNICIEN", "COMPTABLE"]: 
        return True
    if action == "validate" and role in ["DG", "COMPTABLE", "CAISSE"]: 
        return True
    return False

@router.post("/", response_model=BesoinResponse, status_code=status.HTTP_201_CREATED)
async def create_besoin(
    data: BesoinCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    try:
        return service.create_besoin(data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/attente-stock", response_model=List[BesoinResponse])
async def get_besoins_attente_stock(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["GESTIONNAIRE", "ADMIN", "DG"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    from ...models.besoin import StatutBesoin
    return (
        db.query(Besoin)
        .filter(Besoin.statut == StatutBesoin.ATTENTE_STOCK)
        .order_by(Besoin.date_creation.desc())
        .all()
    )

@router.get("/panne/{panne_id}", response_model=List[BesoinResponse])
async def get_besoins_by_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    return service.get_besoins_by_panne(panne_id)

@router.get("/a-valider", response_model=List[BesoinResponse])
async def get_besoins_a_valider(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["DG", "COMPTABLE", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes pour valider")
    service = BesoinService(db)
    return service.get_besoins_a_valider(role)

@router.post("/{besoin_id}/valider")
async def valider_besoin(
    besoin_id: int,
    decision: str = Query(..., pattern="^(APPROUVE|REJETE)$"),
    commentaire: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["DG", "COMPTABLE", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes pour valider")
    service = BesoinService(db)
    try:
        besoin = service.valider_besoin(besoin_id, current_user.id, role, decision, commentaire)
        if not besoin:
            raise HTTPException(status_code=404, detail="Besoin non trouvé")
        return besoin
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[BesoinResponse])
async def get_all_besoins(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(Besoin).order_by(Besoin.date_creation.desc())
    return query.offset(skip).limit(limit).all()

@router.get("/{besoin_id}", response_model=BesoinResponse)
async def get_besoin(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    besoin = service.get_besoin(besoin_id)
    if not besoin:
        raise HTTPException(status_code=404, detail="Besoin non trouvé")
    return besoin

# ✅ NOUVEAU ENDPOINT POUR LA PHASE 2
@router.post("/{besoin_id}/lignes", response_model=BesoinResponse)
async def ajouter_ligne_besoin(
    besoin_id: int,
    data: AjoutLigneRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Ajoute une ligne à un besoin existant (BROUILLON uniquement).
    
    - Vérifie les permissions (create)
    - Appelle BesoinService.ajouter_ligne()
    - Retourne le besoin mis à jour
    """
    if not check_besoin_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = BesoinService(db)
    try:
        besoin = service.ajouter_ligne(besoin_id, data.id_piece, data.quantite)
        return besoin
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Erreur API ajout ligne: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")