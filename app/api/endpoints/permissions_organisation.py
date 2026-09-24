# backend/app/api/endpoints/permissions_organisation.py
# -*- coding: utf-8 -*-
"""
Endpoints de gestion des overrides de permissions par ONG.
Phase 5 — Fondations multi-tenant OKAPI Flotte

Ces endpoints permettent à l'ADMIN ONG de personnaliser les permissions
de ses propres rôles, SANS impacter les autres ONG.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.role import Role
from ...schemas.permission import (
    PermissionResponse,
    RolePermissionAssign,
)
from ...schemas.organisation_role_permission import (
    OrganisationRolePermissionCreate,
    OrganisationRolePermissionUpdate,
    OrganisationRolePermissionResponse,
    PermissionResolutionResponse,
)
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/permissions-organisation", tags=["Permissions ONG"])


# ============================================================================
# HELPERS
# ============================================================================

def _is_platform_admin(user: Utilisateur) -> bool:
    """ADMIN plateforme = organisation_id NULL."""
    return user is not None and user.organisation_id is None


def _verifier_acces_ong(
    current_user: Utilisateur, organisation_id: int, db: Session
) -> None:
    """
    Vérifie que l'utilisateur peut gérer les permissions de cette ONG :
    - ADMIN plateforme → accès total
    - ADMIN ONG → uniquement sa propre ONG
    """
    if _is_platform_admin(current_user):
        return

    # ADMIN ONG
    role_nom = (current_user.role.nom if current_user.role else "").strip().upper()
    if role_nom != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )

    if current_user.organisation_id != organisation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : vous ne pouvez modifier que votre propre organisation",
        )


# ============================================================================
# GET /permissions-organisation/{organisation_id} — Liste des overrides
# ============================================================================

@router.get(
    "/{organisation_id}",
    response_model=List[OrganisationRolePermissionResponse],
    summary="Lister les overrides d'une ONG",
)
@router.get("/{organisation_id}/", response_model=List[OrganisationRolePermissionResponse], include_in_schema=False)
def lister_overrides(
    organisation_id: int,
    role_id: Optional[int] = Query(None, description="Filtrer par rôle"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_acces_ong(current_user, organisation_id, db)
    service = PermissionService(db)
    overrides = service.lister_overrides_ong(organisation_id, id_role=role_id)
    return [OrganisationRolePermissionResponse.model_validate(o) for o in overrides]


# ============================================================================
# GET /permissions-organisation/{organisation_id}/role/{role_id}
# ============================================================================

@router.get(
    "/{organisation_id}/role/{role_id}",
    response_model=List[OrganisationRolePermissionResponse],
    summary="Lister les overrides d'un rôle dans une ONG",
)
@router.get(
    "/{organisation_id}/role/{role_id}/",
    response_model=List[OrganisationRolePermissionResponse],
    include_in_schema=False,
)
def lister_overrides_role(
    organisation_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_acces_ong(current_user, organisation_id, db)
    service = PermissionService(db)
    overrides = service.lister_overrides_ong(organisation_id, id_role=role_id)
    return [OrganisationRolePermissionResponse.model_validate(o) for o in overrides]


# ============================================================================
# POST /permissions-organisation/{organisation_id}/role/{role_id}/attribuer
# ============================================================================

@router.post(
    "/{organisation_id}/role/{role_id}/attribuer",
    response_model=OrganisationRolePermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attribuer/Forcer une permission pour un rôle d'une ONG",
)
@router.post(
    "/{organisation_id}/role/{role_id}/attribuer/",
    response_model=OrganisationRolePermissionResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def attribuer_permission_ong(
    organisation_id: int,
    role_id: int,
    payload: Dict[str, Any] = Body(
        ...,
        example={"permission_code": "MISSION_VALIDER", "accorde": True},
    ),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Crée un override : accorde explicitement une permission à un rôle
    dans une ONG donnée, indépendamment de la valeur par défaut.
    """
    _verifier_acces_ong(current_user, organisation_id, db)

    permission_code = (payload or {}).get("permission_code")
    if not permission_code:
        raise HTTPException(status_code=400, detail="permission_code est obligatoire")

    accorde = bool((payload or {}).get("accorde", True))

    service = PermissionService(db)
    try:
        override = service.attribuer_permission_ong(
            organisation_id=organisation_id,
            id_role=role_id,
            permission_code=permission_code,
            accorde=accorde,
            user_id=current_user.id,
        )
        db.commit()
        return OrganisationRolePermissionResponse.model_validate(override)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# POST /permissions-organisation/{organisation_id}/role/{role_id}/revoquer
# ============================================================================

@router.post(
    "/{organisation_id}/role/{role_id}/revoquer",
    status_code=status.HTTP_200_OK,
    summary="Révoquer une permission d'un rôle d'une ONG",
)
@router.post(
    "/{organisation_id}/role/{role_id}/revoquer/",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def revoquer_override_ong(
    organisation_id: int,
    role_id: int,
    payload: Dict[str, Any] = Body(
        ...,
        example={"permission_code": "MISSION_VALIDER"},
    ),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Supprime l'override → le rôle repasse au comportement par défaut
    (matrice globale role_permissions).
    """
    _verifier_acces_ong(current_user, organisation_id, db)

    permission_code = (payload or {}).get("permission_code")
    if not permission_code:
        raise HTTPException(status_code=400, detail="permission_code est obligatoire")

    service = PermissionService(db)
    try:
        success = service.revoquer_override_permission(
            organisation_id=organisation_id,
            id_role=role_id,
            permission_code=permission_code,
            user_id=current_user.id,
        )
        db.commit()
        return {
            "success": success,
            "message": (
                "Override supprimé" if success else "Aucun override à supprimer"
            ),
            "organisation_id": organisation_id,
            "role_id": role_id,
            "permission_code": permission_code,
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# GET /permissions-organisation/{organisation_id}/resoudre
#     Diagnostic : comment une permission est résolue pour un rôle d'une ONG
# ============================================================================

@router.get(
    "/{organisation_id}/resoudre",
    response_model=PermissionResolutionResponse,
    summary="Diagnostiquer la résolution d'une permission",
)
@router.get(
    "/{organisation_id}/resoudre/",
    response_model=PermissionResolutionResponse,
    include_in_schema=False,
)
def resoudre_permission(
    organisation_id: int,
    role_id: int = Query(..., gt=0),
    permission_code: str = Query(...),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Retourne comment une permission est résolue pour (organisation, rôle) :
    - source = override / global_default / not_found
    - accorde = booléen final
    """
    _verifier_acces_ong(current_user, organisation_id, db)

    service = PermissionService(db)
    resolution = service.resoudre_permission_ong(
        organisation_id=organisation_id,
        id_role=role_id,
        permission_code=permission_code,
    )
    return PermissionResolutionResponse(**resolution)


# ============================================================================
# GET /permissions-organisation/{organisation_id}/mes-permissions
#     Retourne les permissions effectives de l'utilisateur connecté dans cette ONG
# ============================================================================

@router.get(
    "/{organisation_id}/mes-permissions",
    response_model=List[PermissionResponse],
    summary="Mes permissions effectives dans une ONG",
)
@router.get(
    "/{organisation_id}/mes-permissions/",
    response_model=List[PermissionResponse],
    include_in_schema=False,
)
def mes_permissions_ong(
    organisation_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Retourne les permissions EFFECTIVES de l'utilisateur (avec overrides appliqués).
    """
    _verifier_acces_ong(current_user, organisation_id, db)

    service = PermissionService(db)
    role_id = current_user.role_id
    if not role_id:
        return []

    # Toutes les permissions du registre
    all_perms = service.lister_permissions(actif=True)
    result = []
    for perm in all_perms:
        if service.hasPermission(current_user, perm.nom):
            result.append(PermissionResponse.model_validate(perm))
    return result