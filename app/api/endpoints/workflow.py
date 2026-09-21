# backend/app/api/endpoints/workflow.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from typing import List
import logging

from ...core.database import get_db
# ═══ AJOUT 5.17 — Dépendance module ═══
from ...core.dependencies_modules import require_module
# ═══ FIN AJOUT 5.17 ═══
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.workflow_etape import (
    WorkflowEtapeCreate,
    WorkflowEtapeUpdate,
    WorkflowEtapeResponse,
)
from ...services.workflow_service import WorkflowService
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)

# ═══ MODIF 5.17 — require_module sur le router ═══
router = APIRouter(
    prefix="/workflow",
    tags=["Workflow"],
    dependencies=[Depends(require_module("WORKFLOW_PERSONNALISE"))],
)
# ═══ FIN MODIF 5.17 ═══


# ═══ MODIF 5.17 — Ajout BESOIN et CESSION ═══
TYPES_WORKFLOW_VALIDES = {
    "MISSION",
    "RAVITAILLEMENT",
    "INCIDENT",
    "BESOIN",     # ═══ AJOUT 5.17 ═══
    "CESSION",    # ═══ AJOUT 5.17 ═══
}
# ═══ FIN MODIF 5.17 ═══


def _verifier_permission(db: Session, current_user: Utilisateur, permission_code: str) -> None:
    permission_service = PermissionService(db)
    if not permission_service.hasPermission(current_user, permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission refusée : {permission_code} requise",
        )


def _valider_type_workflow(type_workflow: str) -> str:
    if not type_workflow:
        raise HTTPException(status_code=400, detail="Type de workflow manquant")
    type_upper = type_workflow.strip().upper()
    if type_upper not in TYPES_WORKFLOW_VALIDES:
        raise HTTPException(
            status_code=400,
            detail=f"Type de workflow invalide. Valeurs autorisées : {sorted(TYPES_WORKFLOW_VALIDES)}",
        )
    return type_upper


def _verifier_isolation(etape_organisation_id: int, current_user: Utilisateur) -> None:
    if current_user.organisation_id is None:
        return
    if etape_organisation_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : cette étape appartient à une autre organisation",
        )


# ============================================================================
# GET /workflow/{type_workflow}
# ============================================================================
@router.get(
    "/{type_workflow}",
    response_model=List[WorkflowEtapeResponse],
    summary="Lister les étapes d'un workflow",
)
def lister_etapes(
    type_workflow: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "WORKFLOW_VOIR")
    type_wf = _valider_type_workflow(type_workflow)

    if current_user.organisation_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation non définie pour cet utilisateur",
        )

    service = WorkflowService(db)
    try:
        return service.obtenir_etapes(type_wf, current_user.organisation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# POST /workflow/{type_workflow}/etapes
# ============================================================================
@router.post(
    "/{type_workflow}/etapes",
    response_model=WorkflowEtapeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une étape de workflow",
)
def creer_etape(
    type_workflow: str,
    payload: WorkflowEtapeCreate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "WORKFLOW_GERER")
    type_wf = _valider_type_workflow(type_workflow)

    if current_user.organisation_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation non définie pour cet utilisateur",
        )

    service = WorkflowService(db)
    audit_service = AuditService(db)

    data = payload.model_dump()
    data["organisation_id"] = current_user.organisation_id
    data["type_workflow"] = type_wf

    try:
        etape = service.creer_etape(data, user_id=None)
        db.commit()

        audit_service.log_create(
            user_id=current_user.id,
            table_name="workflow_etapes",
            record_id=etape.id,
            new_values={
                "type_workflow": type_wf,
                "ordre": etape.ordre,
                "role_requis": etape.role_requis,
                "permission_requise": etape.permission_requise,
            },
            request=request,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création étape workflow : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return etape


# ============================================================================
# PUT /workflow/etapes/{etape_id}
# ============================================================================
@router.put(
    "/etapes/{etape_id}",
    response_model=WorkflowEtapeResponse,
    summary="Modifier une étape de workflow",
)
def modifier_etape(
    etape_id: int,
    payload: WorkflowEtapeUpdate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "WORKFLOW_GERER")

    service = WorkflowService(db)
    audit_service = AuditService(db)

    etape_existante = service.obtenir_etape(etape_id)
    if not etape_existante:
        raise HTTPException(status_code=404, detail=f"Étape #{etape_id} introuvable")
    _verifier_isolation(etape_existante.organisation_id, current_user)

    old_ordre = etape_existante.ordre
    data = payload.model_dump(exclude_unset=True)

    try:
        etape = service.modifier_etape(etape_id, data, user_id=None)
        db.commit()

        audit_service.log_update(
            user_id=current_user.id,
            table_name="workflow_etapes",
            record_id=etape.id,
            old_values={"ordre": old_ordre},
            new_values={
                "ordre": etape.ordre,
                "role_requis": etape.role_requis,
                "actif": etape.actif,
            },
            request=request,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur modification étape workflow : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return etape


# ============================================================================
# DELETE /workflow/etapes/{etape_id}
# ============================================================================
@router.delete(
    "/etapes/{etape_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une étape de workflow",
)
def supprimer_etape(
    etape_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "WORKFLOW_GERER")

    service = WorkflowService(db)
    audit_service = AuditService(db)

    etape = service.obtenir_etape(etape_id)
    if not etape:
        raise HTTPException(status_code=404, detail=f"Étape #{etape_id} introuvable")
    _verifier_isolation(etape.organisation_id, current_user)

    old_values = {
        "type_workflow": etape.type_workflow.value,
        "ordre": etape.ordre,
        "role_requis": etape.role_requis,
    }

    try:
        service.supprimer_etape(etape_id, user_id=None)
        db.commit()

        audit_service.log_delete(
            user_id=current_user.id,
            table_name="workflow_etapes",
            record_id=etape_id,
            old_values=old_values,
            request=request,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur suppression étape workflow : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return None