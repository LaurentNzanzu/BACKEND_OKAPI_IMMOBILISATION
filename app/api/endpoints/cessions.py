from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import List

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...schemas.cession import CessionCreate, CessionResponse, RebutCreate
from ...schemas.ecriture_comptable import EcritureResponse
from ...services.comptabilite_service import ComptabiliteService

router = APIRouter(prefix="/cessions", tags=["Cessions"])


def check_cession_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "COMPTABLE", "DG"]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def creer_cession(
    data: CessionCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_cession_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    bien = db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
    if not bien:
        raise HTTPException(status_code=404, detail="Bien non trouvé")

    try:
        service = ComptabiliteService(db, cree_par_id=current_user.id)
        cession, ecritures = service.enregistrer_cession(data)
        return {
            "cession": CessionResponse.model_validate(cession),
            "ecritures": ecritures,
            "message": f"Cession enregistrée — {len(ecritures)} écriture(s) générée(s)",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rebut", response_model=List[EcritureResponse], status_code=status.HTTP_201_CREATED)
async def mettre_au_rebut(
    data: RebutCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_cession_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    try:
        service = ComptabiliteService(db, cree_par_id=current_user.id)
        return service.enregistrer_rebut(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
