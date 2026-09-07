from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Any

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.config_inventaire_service import ConfigInventaireService
from ...schemas.config_inventaire import ConfigInventaireResponse, ConfigInventaireUpdate

router = APIRouter(prefix="/config/inventaire", tags=["Configuration Inventaire"])


@router.get("/", response_model=ConfigInventaireResponse)
async def get_config(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
) -> Any:
    """
    Récupère la configuration actuelle du numéro d'inventaire.
    """
    service = ConfigInventaireService(db)
    config = service.get_config()
    return config


@router.put("/", response_model=ConfigInventaireResponse)
async def update_config(
    data: ConfigInventaireUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
) -> Any:
    """
    Met à jour la configuration du numéro d'inventaire.
    """
    service = ConfigInventaireService(db)
    config = service.update_config(data)
    return config