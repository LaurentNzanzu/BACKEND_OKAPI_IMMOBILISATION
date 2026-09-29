from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.dependencies import get_current_organisation_id
from app.core.dependencies_modules import require_module
from app.core.dependencies_permissions import require_permission
from app.services import planning_service

router = APIRouter(
    prefix="/planning",
    tags=["Planning"],
    dependencies=[Depends(require_module("VEHICULE"))],
)


@router.get("/", dependencies=[Depends(require_permission("VEHICULE_VOIR"))])
def get_planning(
    date_debut: datetime = Query(...),
    date_fin: datetime = Query(...),
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    return planning_service.get_planning(db, organisation_id, date_debut, date_fin)