# backend/app/api/endpoints/import_csv.py
"""
Endpoints d'import CSV (STUB Sprint 0).
Sprint 0 — Fondations OKAPI Flotte

Ces endpoints sont réservés pour le Sprint 1+.
Ils vérifient la permission et retournent un message d'attente.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from sqlalchemy.orm import Session
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["Import CSV"])


TYPES_ENTITE_VALIDES = {"vehicules", "chauffeurs", "projets"}


def _verifier_permission(
    db: Session, current_user: Utilisateur, permission_code: str
) -> None:
    permission_service = PermissionService(db)
    if not permission_service.hasPermission(current_user, permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission refusée : {permission_code} requise",
        )


@router.post(
    "/csv/{type_entite}",
    summary="Importer un fichier CSV (stub Sprint 0)",
    description=(
        "Endpoint réservé pour Sprint 1. "
        "Accepte un fichier CSV et retourne un message indiquant que l'import "
        "n'est pas encore implémenté."
    ),
)
async def importer_csv(
    type_entite: str,
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "IMPORT_CSV")

    if type_entite not in TYPES_ENTITE_VALIDES:
        raise HTTPException(
            status_code=400,
            detail=f"Type d'entité invalide. Valeurs autorisées : {sorted(TYPES_ENTITE_VALIDES)}",
        )

    if current_user.organisation_id is None:
        raise HTTPException(
            status_code=403,
            detail="Organisation non définie pour cet utilisateur",
        )

    # Stub Sprint 0 : on retourne juste un message
    return {
        "success": False,
        "message": f"Import {type_entite} prêt mais non implémenté en Sprint 0",
        "type_entite": type_entite,
        "filename": file.filename if file else None,
        "info": "Endpoint réservé pour Sprint 1",
    }