from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.besoin import (
    BesoinCreate,
    BesoinUpdate,
    BesoinResponse,
    AjoutLigneRequest,
    AjoutLigneHorsCatalogueRequest
)
from ...services.besoin_service import BesoinService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.besoin import Besoin

from ...core.dependencies_modules import require_module

router = APIRouter(
    prefix="/besoins",
    tags=["Besoins"],
    dependencies=[Depends(require_module("MAINTENANCE"))],
)


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
        return service.create_besoin(data, organisation_id=current_user.organisation_id)   # ═══ 5.22 ═══
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
    # ═══ 5.22 — Filtre ONG ═══
    query = db.query(Besoin).filter(Besoin.statut == StatutBesoin.ATTENTE_STOCK)
    if current_user.organisation_id is not None:
        query = query.filter(Besoin.organisation_id == current_user.organisation_id)
    return query.order_by(Besoin.date_creation.desc()).all()
    # ═══ FIN 5.22 ═══


@router.get("/panne/{panne_id}", response_model=List[BesoinResponse])
async def get_besoins_by_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    return service.get_besoins_by_panne(panne_id, organisation_id=current_user.organisation_id)   # ═══ 5.22 ═══


@router.get("/a-valider", response_model=List[BesoinResponse])
async def get_besoins_a_valider(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["DG", "COMPTABLE", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes pour valider")
    service = BesoinService(db)
    return service.get_besoins_a_valider(role, organisation_id=current_user.organisation_id)   # ═══ 5.22 ═══


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
        besoin = service.valider_besoin(
            besoin_id,
            current_user.id,
            role,
            decision,
            commentaire,
            organisation_id=current_user.organisation_id,   # ═══ 5.22 ═══
        )
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
    # ═══ 5.22 — Filtre ONG ═══
    query = db.query(Besoin)
    if current_user.organisation_id is not None:
        query = query.filter(Besoin.organisation_id == current_user.organisation_id)
    return query.order_by(Besoin.date_creation.desc()).offset(skip).limit(limit).all()
    # ═══ FIN 5.22 ═══


@router.get("/{besoin_id}", response_model=BesoinResponse)
async def get_besoin(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    besoin = service.get_besoin(besoin_id, organisation_id=current_user.organisation_id)   # ═══ 5.22 ═══
    if not besoin:
        raise HTTPException(status_code=404, detail="Besoin non trouvé")
    return besoin


@router.post("/{besoin_id}/lignes", response_model=BesoinResponse)
async def ajouter_ligne_besoin(
    besoin_id: int,
    data: AjoutLigneRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    try:
        besoin = service.ajouter_ligne(
            besoin_id,
            data.id_piece,
            data.quantite,
            organisation_id=current_user.organisation_id,   # ═══ 5.22 ═══
        )
        return besoin
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Erreur API ajout ligne: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")


@router.post("/{besoin_id}/lignes/hors-catalogue", response_model=BesoinResponse)
async def ajouter_ligne_hors_catalogue(
    besoin_id: int,
    data: AjoutLigneHorsCatalogueRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    try:
        besoin = service.ajouter_ligne_hors_catalogue(
            besoin_id,
            data.designation,
            data.prix_unitaire,
            data.quantite,
            organisation_id=current_user.organisation_id,   # ═══ 5.22 ═══
        )
        return besoin
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Erreur API ajout ligne hors catalogue: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")


@router.delete("/{besoin_id}/lignes/{ligne_id}", response_model=BesoinResponse)
async def supprimer_ligne_besoin(
    besoin_id: int,
    ligne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_besoin_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = BesoinService(db)
    try:
        besoin = service.supprimer_ligne(
            besoin_id,
            ligne_id,
            organisation_id=current_user.organisation_id,   # ═══ 5.22 ═══
        )
        if not besoin:
            raise HTTPException(status_code=404, detail="Besoin non trouvé")
        return besoin
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Erreur API suppression ligne: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")