from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.localisation import LocalisationResponse, LocalisationListResponse, LocalisationCreate
from ...services.localisation_service import LocalisationService

from ...core.dependencies_modules import require_module

router = APIRouter(
    prefix="/localisations",
    tags=["Localisations"],
    dependencies=[Depends(require_module("IMMOBILISATION"))],
)


@router.get("/", response_model=LocalisationListResponse)
@router.get("", response_model=LocalisationListResponse, include_in_schema=False)
async def list_localisations(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = LocalisationService(db)
    items = service.get_all(skip=skip, limit=limit, organisation_id=current_user.organisation_id)  # ═══ 5.22 ═══
    return LocalisationListResponse(
        total=len(items),
        localisations=[LocalisationResponse.model_validate(i) for i in items],
    )


@router.post("/", response_model=LocalisationResponse, status_code=status.HTTP_201_CREATED)
async def create_localisation(
    data: LocalisationCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "COMPTABLE", "GESTIONNAIRE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = LocalisationService(db)
    try:
        return service.create(data, organisation_id=current_user.organisation_id)  # ═══ 5.22 ═══
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=400, detail="Cette localisation existe déjà")
        raise