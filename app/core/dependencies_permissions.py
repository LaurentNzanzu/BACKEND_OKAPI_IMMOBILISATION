from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from .database import get_db
from .security import get_current_user
from ..models.utilisateur import Utilisateur
from ..services.permission_service import PermissionService

logger = logging.getLogger(__name__)


def require_permission(permission_code: str):
    """
    Factory de dépendance FastAPI qui vérifie qu'un utilisateur possède
    une permission granulaire donnée.

    Usage :
        @router.post(
            "/missions/",
            dependencies=[Depends(require_permission("MISSION_CREATE"))],
        )

    Args:
        permission_code: Code de la permission (ex: "MISSION_CREATE")

    Raises:
        ValueError: si le code est vide
        HTTPException 401: si non authentifié
        HTTPException 403: si la permission est absente
    """
    if not permission_code or not str(permission_code).strip():
        raise ValueError("permission_code est obligatoire")

    code_normalized = str(permission_code).strip().upper()

    def dependency(
        current_user: Utilisateur = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Utilisateur:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise",
            )

        permission_service = PermissionService(db)
        if not permission_service.hasPermission(current_user, code_normalized):
            logger.warning(
                f"Permission refusée : utilisateur "
                f"#{getattr(current_user, 'id', '?')} "
                f"({getattr(current_user, 'email', '?')}) "
                f"n'a pas '{code_normalized}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission refusée : {code_normalized} requise",
            )

        return current_user

    return dependency


def require_any_permission(*permission_codes: str):
    """
    Vérifie que l'utilisateur possède AU MOINS UNE des permissions listées.

    Usage :
        Depends(require_any_permission("MISSION_CREATE", "MISSION_VALIDATE_LOG"))
    """
    if not permission_codes:
        raise ValueError("Au moins un permission_code est requis")

    codes_normalized = [
        str(c).strip().upper() for c in permission_codes if c and str(c).strip()
    ]
    if not codes_normalized:
        raise ValueError("Aucun permission_code valide fourni")

    def dependency(
        current_user: Utilisateur = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Utilisateur:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise",
            )

        permission_service = PermissionService(db)
        if not permission_service.verifier_permissions_utilisateur(
            current_user, codes_normalized, require_all=False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Au moins une de ces permissions est requise : "
                    f"{', '.join(codes_normalized)}"
                ),
            )

        return current_user

    return dependency


def require_all_permissions(*permission_codes: str):
    """
    Vérifie que l'utilisateur possède TOUTES les permissions listées.

    Usage :
        Depends(require_all_permissions("MISSION_CREATE", "PROJET_GERER"))
    """
    if not permission_codes:
        raise ValueError("Au moins un permission_code est requis")

    codes_normalized = [
        str(c).strip().upper() for c in permission_codes if c and str(c).strip()
    ]
    if not codes_normalized:
        raise ValueError("Aucun permission_code valide fourni")

    def dependency(
        current_user: Utilisateur = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Utilisateur:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise",
            )

        permission_service = PermissionService(db)
        if not permission_service.verifier_permissions_utilisateur(
            current_user, codes_normalized, require_all=True
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Toutes ces permissions sont requises : "
                    f"{', '.join(codes_normalized)}"
                ),
            )

        return current_user

    return dependency