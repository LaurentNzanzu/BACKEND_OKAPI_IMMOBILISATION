from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Optional

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.etat_service import EtatService

router = APIRouter(prefix="/etats-financiers", tags=["États Financiers"])


@router.get("/fiche-stock")
async def get_fiche_stock(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Génère la fiche de stock."""
    service = EtatService(db)
    return service.get_fiche_stock()


@router.get("/etat-parc")
async def get_etat_parc(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Génère l'état du parc (santé des biens)."""
    service = EtatService(db)
    return service.get_etat_parc()


@router.get("/etat-financier")
async def get_etat_financier(
    exercice: Optional[int] = Query(None, description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Génère l'état financier."""
    service = EtatService(db)
    return service.get_etat_financier(exercice)


@router.get("/etat-sortie")
async def get_etat_sortie(
    exercice: Optional[int] = Query(None, description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Génère l'état de sortie (dépenses par maintenance)."""
    service = EtatService(db)
    return service.get_etat_sortie(exercice)
