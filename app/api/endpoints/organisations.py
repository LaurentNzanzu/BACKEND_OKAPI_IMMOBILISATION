# backend/app/api/endpoints/organisations.py
"""
Endpoints de gestion des organisations (multi-tenant SaaS).
Sprint 0 — Fondations OKAPI Flotte

Réservé aux ADMIN plateforme (utilisateurs sans organisation_id).
Permet de créer, lister, mettre à jour et gérer le cycle de vie
des ONG clientes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.organisation import (
    OrganisationCreate,
    OrganisationUpdate,
    OrganisationResponse,
)
from ...services.organisation_service import OrganisationService
from ...services.workflow_service import WorkflowService
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/organisations", tags=["Organisations"])


# ============================================================================
# HELPERS
# ============================================================================

def _verifier_admin_plateforme(current_user: Utilisateur) -> None:
    """
    Vérifie que l'utilisateur est un ADMIN plateforme.
    Un ADMIN plateforme = utilisateur sans organisation_id.
    """
    if current_user.organisation_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'ADMIN plateforme",
        )


def _verifier_permission(
    db: Session, current_user: Utilisateur, permission_code: str
) -> None:
    permission_service = PermissionService(db)
    if not permission_service.hasPermission(current_user, permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission refusée : {permission_code} requise",
        )


# ============================================================================
# ROUTE 1 — POST /organisations
# ============================================================================

@router.post(
    "/",
    response_model=OrganisationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une organisation",
    description="Crée une nouvelle ONG cliente (réservé ADMIN plateforme).",
)
def creer_organisation(
    payload: OrganisationCreate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    workflow_service = WorkflowService(db)
    audit_service = AuditService(db)

    data = payload.model_dump()

    try:
        organisation = service.creer_organisation(data, user_id=None)
        db.commit()

        # Initialiser le workflow par défaut pour cette nouvelle organisation
        try:
            workflow_service.initialiser_workflow_par_defaut(
                organisation_id=organisation.id,
                user_id=None,
            )
            db.commit()
        except Exception as e_wf:
            # Non bloquant : on log mais on ne fait pas échouer la création
            logger.warning(
                f"Initialisation workflow par défaut échouée pour org #{organisation.id} : {e_wf}"
            )
            db.rollback()

        audit_service.log_create(
            user_id=current_user.id,
            table_name="organisations",
            record_id=organisation.id,
            new_values={
                "nom": organisation.nom,
                "code": organisation.code,
                "plan_abonnement": (
                    organisation.plan_abonnement.value
                    if organisation.plan_abonnement
                    else None
                ),
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création organisation : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return organisation


# ============================================================================
# ROUTE 2 — GET /organisations
# ============================================================================

@router.get(
    "/",
    response_model=List[OrganisationResponse],
    summary="Lister les organisations",
    description="Liste les organisations (réservé ADMIN plateforme).",
)
def lister_organisations(
    statut: Optional[str] = Query(None, description="Filtrer par statut (ACTIF, SUSPENDU, EXPIRE)"),
    search: Optional[str] = Query(None, description="Recherche sur nom/code/email"),
    skip: int = Query(0, ge=0, description="Pagination - offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination - limite"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    return service.lister_organisations(
        statut=statut,
        search=search,
        skip=skip,
        limit=limit,
    )


# ============================================================================
# ROUTE 3 — GET /organisations/{org_id}
# ============================================================================

@router.get(
    "/{org_id}",
    response_model=OrganisationResponse,
    summary="Obtenir une organisation",
    description="Retourne les détails d'une organisation (réservé ADMIN plateforme).",
)
def obtenir_organisation(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    organisation = service.obtenir_organisation(org_id)

    if not organisation:
        raise HTTPException(
            status_code=404, detail=f"Organisation #{org_id} introuvable"
        )

    return organisation


# ============================================================================
# ROUTE 4 — PUT /organisations/{org_id}
# ============================================================================

@router.put(
    "/{org_id}",
    response_model=OrganisationResponse,
    summary="Modifier une organisation",
    description="Met à jour les champs modifiables d'une organisation.",
)
def modifier_organisation(
    org_id: int,
    payload: OrganisationUpdate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    audit_service = AuditService(db)

    organisation_existante = service.obtenir_organisation(org_id)
    if not organisation_existante:
        raise HTTPException(
            status_code=404, detail=f"Organisation #{org_id} introuvable"
        )

    old_values = {
        "nom": organisation_existante.nom,
        "email_admin": organisation_existante.email_admin,
        "plan_abonnement": (
            organisation_existante.plan_abonnement.value
            if organisation_existante.plan_abonnement
            else None
        ),
        "devise": organisation_existante.devise,
    }

    data = payload.model_dump(exclude_unset=True)

    try:
        organisation = service.mettre_a_jour(org_id, data, user_id=None)
        db.commit()

        audit_service.log_update(
            user_id=current_user.id,
            table_name="organisations",
            record_id=organisation.id,
            old_values=old_values,
            new_values={
                "nom": organisation.nom,
                "email_admin": organisation.email_admin,
                "plan_abonnement": (
                    organisation.plan_abonnement.value
                    if organisation.plan_abonnement
                    else None
                ),
                "devise": organisation.devise,
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur modification organisation : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return organisation


# ============================================================================
# ROUTE 5 — POST /organisations/{org_id}/suspendre
# ============================================================================

@router.post(
    "/{org_id}/suspendre",
    response_model=OrganisationResponse,
    summary="Suspendre une organisation",
    description="Suspend une organisation (blocage d'accès).",
)
def suspendre_organisation(
    org_id: int,
    payload: dict = Body(..., example={"motif": "Impayé depuis 3 mois"}),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    motif = (payload or {}).get("motif")
    if not motif or not str(motif).strip():
        raise HTTPException(
            status_code=400, detail="Le motif de suspension est obligatoire"
        )

    service = OrganisationService(db)
    audit_service = AuditService(db)

    try:
        organisation = service.suspendre(
            org_id, motif=str(motif).strip(), user_id=None
        )
        db.commit()

        audit_service.log_action(
            user_id=current_user.id,
            table_name="organisations",
            record_id=organisation.id,
            action="SUSPENSION",
            nouvelles_valeurs={"motif": motif, "statut": "SUSPENDU"},
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur suspension organisation : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return organisation


# ============================================================================
# ROUTE 6 — POST /organisations/{org_id}/reactiver
# ============================================================================

@router.post(
    "/{org_id}/reactiver",
    response_model=OrganisationResponse,
    summary="Réactiver une organisation",
    description="Réactive une organisation suspendue.",
)
def reactiver_organisation(
    org_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    audit_service = AuditService(db)

    try:
        organisation = service.reactiver(org_id, user_id=None)
        db.commit()

        audit_service.log_action(
            user_id=current_user.id,
            table_name="organisations",
            record_id=organisation.id,
            action="REACTIVATION",
            nouvelles_valeurs={"statut": "ACTIF"},
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur réactivation organisation : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return organisation