# backend/app/api/endpoints/permissions.py
# -*- coding: utf-8 -*-
"""
Endpoints de gestion des permissions granulaires (RBAC).
Sprint 0 — Fondations multi-tenant OKAPI Flotte

Permet de lister, créer, modifier, supprimer des permissions
et d'attribuer / révoquer des permissions pour des rôles.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.permission import (
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse,
    RolePermissionAssign,
    RolePermissionAssignCode,
)
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/permissions", tags=["Permissions"])


# ============================================================================
# HELPERS
# ============================================================================

def _verifier_permission(
    db: Session, current_user: Utilisateur, permission_code: str
) -> None:
    """Vérifie que l'utilisateur possède la permission requise ou est ADMIN."""
    permission_service = PermissionService(db)
    if not permission_service.hasPermission(current_user, permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission refusée : {permission_code} requise",
        )


# ═══════════════ AJOUT 5.11 — HELPER ═══════════════
def _verifier_admin_plateforme(current_user: Utilisateur) -> None:
    """
    Vérifie que l'utilisateur est un ADMIN PLATEFORME strict.

    Un ADMIN PLATEFORME est identifié par :
    - organisation_id = NULL
    - role.nom == "ADMIN"

    Bloque tout ADMIN ONG qui tenterait de créer/modifier/supprimer
    des permissions GLOBALES (les permissions globales sont partagées
    par toutes les ONG, seul l'ADMIN plateforme peut les gérer).

    Note : pour personnaliser les permissions de SES rôles, l'ADMIN ONG
    doit utiliser les endpoints /permissions-organisation/ (override local).
    """
    if not getattr(current_user, "is_platform_admin", False):
        logger.warning(
            f"Tentative d'accès non autorisé aux permissions globales : "
            f"user #{getattr(current_user, 'id', '?')} "
            f"({getattr(current_user, 'email', '?')}) — "
            f"organisation_id={getattr(current_user, 'organisation_id', '?')}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Accès réservé à l'ADMIN plateforme. "
                "Les permissions globales ne peuvent pas être modifiées par un ADMIN ONG. "
                "Utilisez /permissions-organisation/ pour personnaliser les permissions de votre ONG."
            ),
        )
# ═══════════════ AJOUT 5.11 — HELPER (FIN) ═══════════════


# ============================================================================
# 1. LISTER LES PERMISSIONS
# ============================================================================

@router.get(
    "/",
    response_model=List[PermissionResponse],
    summary="Lister toutes les permissions",
    description="Retourne la liste des permissions avec filtres optionnels par module, statut actif et recherche textuelle.",
)
def lister_permissions(
    module: Optional[str] = Query(None, description="Filtrer par module (ex: BIENS, MISSIONS)"),
    actif: Optional[bool] = Query(None, description="Filtrer par statut actif"),
    search: Optional[str] = Query(None, description="Recherche sur le nom ou la description"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = PermissionService(db)
    return service.lister_permissions(
        module=module,
        actif=actif,
        search=search,
    )


# ============================================================================
# 2. LISTER LES MODULES
# ============================================================================

@router.get(
    "/modules",
    response_model=List[str],
    summary="Lister les modules distincts",
    description="Retourne la liste de tous les modules distincts existants dans les permissions.",
)
@router.get(
    "/modules/",
    response_model=List[str],
    include_in_schema=False,
)
def lister_modules(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = PermissionService(db)
    return service.lister_modules()


# ============================================================================
# 3. MES PERMISSIONS (UTILISATEUR CONNECTÉ)
# ============================================================================

@router.get(
    "/mes-permissions",
    response_model=List[PermissionResponse],
    summary="Obtenir mes permissions",
    description="Retourne la liste des permissions associées au rôle de l'utilisateur connecté.",
)
@router.get(
    "/mes-permissions/",
    response_model=List[PermissionResponse],
    include_in_schema=False,
)
def mes_permissions(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = PermissionService(db)
    role_id = getattr(current_user, "role_id", None)
    if not role_id:
        role = getattr(current_user, "role", None)
        role_id = getattr(role, "id_role", None) if role else None

    if not role_id:
        return []

    return service.lister_permissions_role(role_id)


# ============================================================================
# 4. LISTER LES PERMISSIONS D'UN RÔLE
# ============================================================================

@router.get(
    "/role/{role_id}",
    response_model=List[PermissionResponse],
    summary="Lister les permissions d'un rôle",
    description="Retourne toutes les permissions attribuées à un rôle spécifique.",
)
@router.get(
    "/role/{role_id}/",
    response_model=List[PermissionResponse],
    include_in_schema=False,
)
def lister_permissions_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = PermissionService(db)
    try:
        return service.lister_permissions_role(role_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# 5. OBTENIR UNE PERMISSION PAR ID
# ============================================================================

@router.get(
    "/{id_permission}",
    response_model=PermissionResponse,
    summary="Obtenir une permission",
    description="Retourne les détails d'une permission par son ID.",
)
@router.get(
    "/{id_permission}/",
    response_model=PermissionResponse,
    include_in_schema=False,
)
def obtenir_permission(
    id_permission: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = PermissionService(db)
    permission = service.obtenir_permission(id_permission)
    if not permission:
        raise HTTPException(
            status_code=404,
            detail=f"Permission #{id_permission} introuvable",
        )
    return permission


# ============================================================================
# 6. CRÉER UNE PERMISSION (ADMIN PLATEFORME)
# ============================================================================

@router.post(
    "/",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une permission",
    description="Crée une nouvelle permission (réservé à l'ADMIN plateforme).",
)
def creer_permission(
    payload: PermissionCreate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    # ═══ MODIF 5.11 — AJOUT appel ═══
    _verifier_admin_plateforme(current_user)
    # ═══ MODIF 5.11 — AJOUT appel (FIN) ═══
    _verifier_permission(db, current_user, "PERMISSION_GERER")

    service = PermissionService(db)
    try:
        permission = service.creer_permission(
            nom=payload.nom,
            module=payload.module,
            action=payload.action,
            description=payload.description,
            actif=payload.actif,
            user_id=current_user.id,
        )
        db.commit()
        return permission
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création permission : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


# ============================================================================
# 7. MODIFIER UNE PERMISSION (ADMIN PLATEFORME)
# ============================================================================

@router.put(
    "/{id_permission}",
    response_model=PermissionResponse,
    summary="Modifier une permission",
    description="Met à jour une permission existante (réservé à l'ADMIN plateforme).",
)
@router.put(
    "/{id_permission}/",
    response_model=PermissionResponse,
    include_in_schema=False,
)
def modifier_permission(
    id_permission: int,
    payload: PermissionUpdate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    # ═══ MODIF 5.11 — AJOUT appel ═══
    _verifier_admin_plateforme(current_user)
    # ═══ MODIF 5.11 — AJOUT appel (FIN) ═══
    _verifier_permission(db, current_user, "PERMISSION_GERER")

    service = PermissionService(db)
    data = payload.model_dump(exclude_unset=True)

    try:
        permission = service.mettre_a_jour_permission(
            id_permission=id_permission,
            data=data,
            user_id=current_user.id,
        )
        db.commit()
        return permission
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur modification permission : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


# ============================================================================
# 8. SUPPRIMER UNE PERMISSION (ADMIN PLATEFORME)
# ============================================================================

@router.delete(
    "/{id_permission}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une permission",
    description="Supprime une permission et la détache de tous les rôles associés (réservé à l'ADMIN plateforme).",
)
@router.delete(
    "/{id_permission}/",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
def supprimer_permission(
    id_permission: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    # ═══ MODIF 5.11 — AJOUT appel ═══
    _verifier_admin_plateforme(current_user)
    # ═══ MODIF 5.11 — AJOUT appel (FIN) ═══
    _verifier_permission(db, current_user, "PERMISSION_GERER")

    service = PermissionService(db)
    try:
        service.supprimer_permission(id_permission=id_permission, user_id=current_user.id)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur suppression permission : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


# ============================================================================
# 9. ATTRIBUER UNE PERMISSION À UN RÔLE (ADMIN PLATEFORME)
# ============================================================================

@router.post(
    "/role/{role_id}/attribuer",
    summary="Attribuer des permissions à un rôle",
    description="Attribue une ou plusieurs permissions à un rôle donné (réservé à l'ADMIN plateforme).",
)
@router.post(
    "/role/{role_id}/attribuer/",
    include_in_schema=False,
)
def attribuer_permissions_role(
    role_id: int,
    payload: RolePermissionAssign = Body(...),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    # ═══ MODIF 5.11 — AJOUT appel ═══
    _verifier_admin_plateforme(current_user)
    # ═══ MODIF 5.11 — AJOUT appel (FIN) ═══
    _verifier_permission(db, current_user, "PERMISSION_GERER")

    service = PermissionService(db)
    nb_attribuees = 0

    try:
        for perm_id in payload.permission_ids:
            perm = service.obtenir_permission(perm_id)
            if perm and service.attribuer_permission(role_id, perm.nom, user_id=current_user.id):
                nb_attribuees += 1

        db.commit()
        return {
            "message": f"{nb_attribuees} permission(s) attribuée(s) avec succès au rôle #{role_id}",
            "role_id": role_id,
            "permissions_actuelles": [p.nom for p in service.lister_permissions_role(role_id)],
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur attribution permission : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


# ============================================================================
# 10. RÉVOQUER UNE PERMISSION D'UN RÔLE (ADMIN PLATEFORME)
# ============================================================================

@router.post(
    "/role/{role_id}/revoquer",
    summary="Révoquer des permissions d'un rôle",
    description="Révoque une ou plusieurs permissions d'un rôle donné (réservé à l'ADMIN plateforme).",
)
@router.post(
    "/role/{role_id}/revoquer/",
    include_in_schema=False,
)
def revoquer_permissions_role(
    role_id: int,
    payload: RolePermissionAssign = Body(...),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    # ═══ MODIF 5.11 — AJOUT appel ═══
    _verifier_admin_plateforme(current_user)
    # ═══ MODIF 5.11 — AJOUT appel (FIN) ═══
    _verifier_permission(db, current_user, "PERMISSION_GERER")

    service = PermissionService(db)
    nb_revoquees = 0

    try:
        for perm_id in payload.permission_ids:
            perm = service.obtenir_permission(perm_id)
            if perm and service.revoquer_permission(role_id, perm.nom, user_id=current_user.id):
                nb_revoquees += 1

        db.commit()
        return {
            "message": f"{nb_revoquees} permission(s) révoquée(s) avec succès du rôle #{role_id}",
            "role_id": role_id,
            "permissions_actuelles": [p.nom for p in service.lister_permissions_role(role_id)],
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur révocation permission : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")