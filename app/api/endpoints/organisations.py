# backend/app/api/endpoints/organisations.py
"""
Endpoints de gestion des organisations (multi-tenant SaaS).
Phase 5 — Retour admin_credentials + gestion modules activables.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.organisation import (
    OrganisationCreate,
    OrganisationUpdate,
    OrganisationResponse,
    OrganisationCreatedResponse,
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
# ROUTE 1 — POST /organisations (avec création auto admin + credentials)
# ============================================================================

@router.post(
    "/",
    response_model=OrganisationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer une organisation (+ admin auto)",
    description=(
        "Crée une nouvelle ONG cliente, active les modules selon le plan, "
        "et génère un compte administrateur avec mot de passe temporaire."
    ),
)
@router.post("/", response_model=OrganisationCreatedResponse, include_in_schema=False)
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
        organisation, credentials = service.creer_organisation(
            data, user_id=current_user.id, creer_admin=True
        )
        db.commit()

        # Initialiser le workflow par défaut
        try:
            workflow_service.initialiser_workflow_par_defaut(
                organisation_id=organisation.id,
                user_id=current_user.id,
            )
            db.commit()
        except Exception as e_wf:
            logger.warning(
                f"Initialisation workflow par défaut échouée pour org "
                f"#{organisation.id} : {e_wf}"
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
                "modules_actifs": organisation.get_modules_actifs(),
                "admin_cree": bool(credentials),
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

    # Construire la réponse enrichie
    response_data = OrganisationResponse.model_validate(organisation).model_dump()
    response_data["modules_actifs"] = organisation.get_modules_actifs()
    response_data["admin_email"] = credentials["admin_email"] if credentials else organisation.email_admin
    response_data["admin_mot_de_passe_temporaire"] = (
        credentials.get("admin_mot_de_passe_temporaire") if credentials else None
    )
    response_data["admin_doit_changer_mdp"] = True

    return OrganisationCreatedResponse(**response_data)


# ============================================================================
# ROUTE 2 — GET /organisations
# ============================================================================

@router.get(
    "/",
    response_model=List[OrganisationResponse],
    summary="Lister les organisations",
)
@router.get("", response_model=List[OrganisationResponse], include_in_schema=False)
def lister_organisations(
    statut: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    orgs = service.lister_organisations(
        statut=statut, search=search, skip=skip, limit=limit
    )
    # Enrichir avec modules_actifs
    result = []
    for org in orgs:
        data = OrganisationResponse.model_validate(org).model_dump()
        data["modules_actifs"] = org.get_modules_actifs()
        result.append(OrganisationResponse(**data))
    return result


# ============================================================================
# ROUTE 3 — GET /organisations/{org_id}
# ============================================================================

@router.get(
    "/{org_id}",
    response_model=OrganisationResponse,
    summary="Obtenir une organisation",
)
@router.get("/{org_id}/", response_model=OrganisationResponse, include_in_schema=False)
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
        raise HTTPException(status_code=404, detail=f"Organisation #{org_id} introuvable")

    data = OrganisationResponse.model_validate(organisation).model_dump()
    data["modules_actifs"] = organisation.get_modules_actifs()
    return OrganisationResponse(**data)


# ============================================================================
# ROUTE 4 — PUT /organisations/{org_id}
# ============================================================================

@router.put(
    "/{org_id}",
    response_model=OrganisationResponse,
    summary="Modifier une organisation",
)
@router.put("/{org_id}/", response_model=OrganisationResponse, include_in_schema=False)
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
        raise HTTPException(status_code=404, detail=f"Organisation #{org_id} introuvable")

    old_values = {
        "nom": organisation_existante.nom,
        "email_admin": organisation_existante.email_admin,
        "plan_abonnement": (
            organisation_existante.plan_abonnement.value
            if organisation_existante.plan_abonnement
            else None
        ),
        "devise": organisation_existante.devise,
        "modules_actifs": organisation_existante.get_modules_actifs(),
    }

    data = payload.model_dump(exclude_unset=True)

    try:
        organisation = service.mettre_a_jour(org_id, data, user_id=current_user.id)
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
                "modules_actifs": organisation.get_modules_actifs(),
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

    data_resp = OrganisationResponse.model_validate(organisation).model_dump()
    data_resp["modules_actifs"] = organisation.get_modules_actifs()
    return OrganisationResponse(**data_resp)


# ============================================================================
# ROUTE 5 — POST /organisations/{org_id}/suspendre
# ============================================================================

@router.post(
    "/{org_id}/suspendre",
    response_model=OrganisationResponse,
    summary="Suspendre une organisation",
)
@router.post(
    "/{org_id}/suspendre/",
    response_model=OrganisationResponse,
    include_in_schema=False,
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
        raise HTTPException(status_code=400, detail="Le motif de suspension est obligatoire")

    service = OrganisationService(db)
    audit_service = AuditService(db)

    try:
        organisation = service.suspendre(org_id, motif=str(motif).strip(), user_id=current_user.id)
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
)
@router.post(
    "/{org_id}/reactiver/",
    response_model=OrganisationResponse,
    include_in_schema=False,
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
        organisation = service.reactiver(org_id, user_id=current_user.id)
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


# ============================================================================
# ROUTES MODULES — /organisations/{org_id}/modules
# ============================================================================

@router.get(
    "/{org_id}/modules",
    summary="Modules actifs d'une ONG",
)
@router.get("/{org_id}/modules/", include_in_schema=False)
def get_modules_ong(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    service = OrganisationService(db)
    organisation = service.obtenir_organisation(org_id)
    if not organisation:
        raise HTTPException(status_code=404, detail=f"Organisation #{org_id} introuvable")

    return {
        "organisation_id": org_id,
        "plan": organisation.plan_abonnement.value if organisation.plan_abonnement else None,
        "modules_actifs": organisation.get_modules_actifs(),
        "total": len(organisation.get_modules_actifs()),
    }


@router.put(
    "/{org_id}/modules",
    summary="Mettre à jour les modules actifs d'une ONG",
)
@router.put("/{org_id}/modules/", include_in_schema=False)
def update_modules_ong(
    org_id: int,
    payload: dict = Body(..., example={"modules_actifs": ["MISSION", "CARBURANT"]}),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    modules = (payload or {}).get("modules_actifs")
    if modules is None or not isinstance(modules, list):
        raise HTTPException(
            status_code=400,
            detail="Le champ 'modules_actifs' doit être une liste",
        )

    service = OrganisationService(db)
    audit_service = AuditService(db)

    try:
        organisation = service.mettre_a_jour_modules(
            org_id, modules, user_id=current_user.id
        )
        db.commit()

        audit_service.log_action(
            user_id=current_user.id,
            table_name="organisations",
            record_id=org_id,
            action="UPDATE_MODULES",
            nouvelles_valeurs={
                "modules_actifs": organisation.get_modules_actifs(),
                "total": len(organisation.get_modules_actifs()),
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "organisation_id": org_id,
        "modules_actifs": organisation.get_modules_actifs(),
        "total": len(organisation.get_modules_actifs()),
    }


@router.post(
    "/{org_id}/modules/activer/{module_code}",
    summary="Activer un module pour une ONG",
)
@router.post(
    "/{org_id}/modules/activer/{module_code}/",
    include_in_schema=False,
)
def activer_module(
    org_id: int,
    module_code: str,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    from ...core.module_registry import module_existe
    code = module_code.strip().upper()
    if not module_existe(code):
        raise HTTPException(status_code=400, detail=f"Module '{module_code}' inconnu")

    service = OrganisationService(db)
    organisation = service.obtenir_organisation(org_id)
    if not organisation:
        raise HTTPException(status_code=404, detail=f"Organisation #{org_id} introuvable")

    current = organisation.get_modules_actifs()
    if code in current:
        return {
            "organisation_id": org_id,
            "message": f"Module '{code}' déjà actif",
            "modules_actifs": current,
        }

    current.append(code)
    try:
        organisation = service.mettre_a_jour_modules(org_id, current, user_id=current_user.id)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "organisation_id": org_id,
        "message": f"Module '{code}' activé",
        "modules_actifs": organisation.get_modules_actifs(),
    }


@router.post(
    "/{org_id}/modules/desactiver/{module_code}",
    summary="Désactiver un module pour une ONG",
)
@router.post(
    "/{org_id}/modules/desactiver/{module_code}/",
    include_in_schema=False,
)
def desactiver_module(
    org_id: int,
    module_code: str,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_admin_plateforme(current_user)
    _verifier_permission(db, current_user, "ORGANISATION_GERER")

    code = module_code.strip().upper()

    service = OrganisationService(db)
    organisation = service.obtenir_organisation(org_id)
    if not organisation:
        raise HTTPException(status_code=404, detail=f"Organisation #{org_id} introuvable")

    current = organisation.get_modules_actifs()
    if code not in current:
        return {
            "organisation_id": org_id,
            "message": f"Module '{code}' déjà inactif",
            "modules_actifs": current,
        }

    current.remove(code)
    try:
        organisation = service.mettre_a_jour_modules(org_id, current, user_id=current_user.id)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "organisation_id": org_id,
        "message": f"Module '{code}' désactivé",
        "modules_actifs": organisation.get_modules_actifs(),
    }