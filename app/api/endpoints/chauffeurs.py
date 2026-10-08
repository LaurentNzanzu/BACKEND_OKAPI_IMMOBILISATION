from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.dependencies import get_current_organisation_id
from app.core.dependencies_modules import require_module
from app.core.dependencies_permissions import require_permission
from app.schemas.chauffeur import ChauffeurCreate, ChauffeurUpdate, ChauffeurRead
from app.services import chauffeur_service
from app.services.chauffeur_service import ChauffeurQuotaExceeded, ChauffeurUserConflict, ChauffeurPermisConflict

router = APIRouter(
    prefix="/chauffeurs",
    tags=["Chauffeurs"],
    dependencies=[Depends(require_module("CHAUFFEUR"))],
)


from datetime import datetime

@router.get("/", response_model=list[ChauffeurRead], dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def list_chauffeurs(
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    skip: int = 0,
    limit: int = Query(100, le=500),
    statut: str | None = None,
    search: str | None = None,
):
    return chauffeur_service.list_chauffeurs(
        db, organisation_id, skip=skip, limit=limit, statut=statut, search=search
    )


@router.get("/disponibles", response_model=list[ChauffeurRead], dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def get_chauffeurs_disponibles(
    date_debut: datetime = Query(...),
    date_fin: datetime = Query(...),
    categorie_permis: str | None = None,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        return chauffeur_service.get_chauffeurs_disponibles(
            db, organisation_id, date_debut=date_debut, date_fin=date_fin, categorie_permis=categorie_permis
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/expirations", dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def get_expirations(
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    return chauffeur_service.verifier_expirations(db, organisation_id=organisation_id)


@router.get("/{chauffeur_id}", response_model=ChauffeurRead, dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def get_chauffeur(
    chauffeur_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    obj = chauffeur_service.get_chauffeur(db, chauffeur_id, organisation_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Chauffeur introuvable")
    return obj


@router.post("/", response_model=ChauffeurRead, status_code=201, dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def create_chauffeur(
    payload: ChauffeurCreate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        return chauffeur_service.create_chauffeur(db, payload, organisation_id)
    except (ChauffeurQuotaExceeded, ChauffeurUserConflict, ChauffeurPermisConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{chauffeur_id}", response_model=ChauffeurRead, dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def update_chauffeur(
    chauffeur_id: int,
    payload: ChauffeurUpdate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    try:
        obj = chauffeur_service.update_chauffeur(db, chauffeur_id, payload, organisation_id)
    except (ChauffeurUserConflict, ChauffeurPermisConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not obj:
        raise HTTPException(status_code=404, detail="Chauffeur introuvable")
    return obj


@router.delete("/{chauffeur_id}", status_code=204, dependencies=[Depends(require_permission("CHAUFFEUR_GERER"))])
def delete_chauffeur(
    chauffeur_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    ok = chauffeur_service.delete_chauffeur(db, chauffeur_id, organisation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chauffeur introuvable")