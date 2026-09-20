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
# 6. CRÉER UNE PERMISSION (ADMIN)
# ============================================================================

@router.post(
    "/",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une permission",
    description="Crée une nouvelle permission (réservé aux administrateurs).",
)
def creer_permission(
    payload: PermissionCreate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
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
# 7. MODIFIER UNE PERMISSION (ADMIN)
# ============================================================================

@router.put(
    "/{id_permission}",
    response_model=PermissionResponse,
    summary="Modifier une permission",
    description="Met à jour une permission existante (réservé aux administrateurs).",
)
def modifier_permission(
    id_permission: int,
    payload: PermissionUpdate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
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
# 8. SUPPRIMER UNE PERMISSION (ADMIN)
# ============================================================================

@router.delete(
    "/{id_permission}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une permission",
    description="Supprime une permission et la détache de tous les rôles associés.",
)
def supprimer_permission(
    id_permission: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
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
# 9. ATTRIBUER UNE PERMISSION À UN RÔLE
# ============================================================================

@router.post(
    "/role/{role_id}/attribuer",
    summary="Attribuer des permissions à un rôle",
    description="Attribue une ou plusieurs permissions à un rôle donné.",
)
def attribuer_permissions_role(
    role_id: int,
    payload: RolePermissionAssign = Body(...),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
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
# 10. RÉVOQUER UNE PERMISSION D'UN RÔLE
# ============================================================================

@router.post(
    "/role/{role_id}/revoquer",
    summary="Révoquer des permissions d'un rôle",
    description="Révoque une ou plusieurs permissions d'un rôle donné.",
)
def revoquer_permissions_role(
    role_id: int,
    payload: RolePermissionAssign = Body(...),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
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