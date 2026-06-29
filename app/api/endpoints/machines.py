from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from ...core.database import get_db
from ...api.dependencies import require_any_roles, BIENS_VIEW_ROLES
from ...models.machine import Machine
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/machines", tags=["Machines"])


@router.get("/")
async def get_machines(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    fabricant: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_any_roles(BIENS_VIEW_ROLES)),
):
    query = db.query(Machine)
    if fabricant:
        query = query.filter(Machine.fabricant == fabricant)
    machines = query.offset(skip).limit(limit).all()
    return {"total": len(machines), "machines": machines}


@router.get("/{bien_id}")
async def get_machine(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_any_roles(BIENS_VIEW_ROLES)),
):
    machine = db.query(Machine).filter(Machine.id_bien == bien_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine non trouvée")
    return machine
