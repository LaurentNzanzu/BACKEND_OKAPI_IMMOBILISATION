from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import logging

from ...core.database import get_db
# ═══ AJOUT 5.16 — Dépendance module ═══
from ...core.dependencies_modules import require_module
# ═══ FIN AJOUT 5.16 ═══
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.projet import (
    ProjetCreate,
    ProjetUpdate,
    ProjetResponse,
)
from ...services.projet_service import ProjetService
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)

# ═══ MODIF 5.16 — require_module sur le router ═══
router = APIRouter(
    prefix="/projets",
    tags=["Projets"],
    dependencies=[Depends(require_module("PROJET"))],
)
# ═══ FIN MODIF 5.16 ═══


# ============================================================================
# HELPERS (inchangés)
# ============================================================================

def _verifier_permission(
    db: Session, current_user: Utilisateur, permission_code: str
) -> None:
    permission_service = PermissionService(db)
    if not permission_service.hasPermission(current_user, permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission refusée : {permission_code} requise",
        )


def _verifier_isolation(projet_organisation_id: int, current_user: Utilisateur) -> None:
    """Vérifie que l'utilisateur peut accéder à ce projet (multi-tenant)."""
    if current_user.organisation_id is None:
        return
    if projet_organisation_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : ce projet appartient à une autre organisation",
        )


def _resoudre_organisation_id(current_user: Utilisateur, payload_org_id: Optional[int] = None) -> int:
    """Détermine l'organisation_id effectif pour la création d'un projet."""
    if current_user.organisation_id is None:
        if payload_org_id is None:
            raise HTTPException(
                status_code=400,
                detail="organisation_id est obligatoire pour un ADMIN plateforme",
            )
        return payload_org_id
    if payload_org_id is not None and payload_org_id != current_user.organisation_id:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez créer un projet que dans votre organisation",
        )
    return current_user.organisation_id


# ============================================================================
# ROUTE 1 — POST /projets
# ============================================================================

@router.post(
    "/",
    response_model=ProjetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un projet",
)
def creer_projet(
    payload: ProjetCreate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "PROJET_GERER")

    organisation_id = _resoudre_organisation_id(
        current_user, payload_org_id=payload.organisation_id
    )

    service = ProjetService(db)
    audit_service = AuditService(db)

    data = payload.model_dump()
    data["organisation_id"] = organisation_id

    try:
        projet = service.creer_projet(data, user_id=None)
        db.commit()

        audit_service.log_create(
            user_id=current_user.id,
            table_name="projets",
            record_id=projet.id,
            new_values={
                "code": projet.code,
                "nom": projet.nom,
                "bailleur": projet.bailleur,
                "budget_annuel": float(projet.budget_annuel or 0),
                "organisation_id": projet.organisation_id,
            },
            request=request,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création projet : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return projet


# ============================================================================
# ROUTE 2 — GET /projets
# ============================================================================

@router.get(
    "/",
    response_model=List[ProjetResponse],
    summary="Lister les projets",
)
def lister_projets(
    est_actif: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "PROJET_VOIR")

    if current_user.organisation_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation non définie pour cet utilisateur",
        )

    service = ProjetService(db)
    return service.lister_projets(
        organisation_id=current_user.organisation_id,
        est_actif=est_actif,
        search=search,
    )


# ============================================================================
# ROUTE 3 — GET /projets/{projet_id}
# ============================================================================

@router.get(
    "/{projet_id}",
    response_model=ProjetResponse,
    summary="Obtenir un projet",
)
def obtenir_projet(
    projet_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "PROJET_VOIR")

    service = ProjetService(db)
    projet = service.obtenir_projet(projet_id)

    if not projet:
        raise HTTPException(status_code=404, detail=f"Projet #{projet_id} introuvable")

    _verifier_isolation(projet.organisation_id, current_user)

    return projet


# ============================================================================
# ROUTE 4 — PUT /projets/{projet_id}
# ============================================================================

@router.put(
    "/{projet_id}",
    response_model=ProjetResponse,
    summary="Modifier un projet",
)
def modifier_projet(
    projet_id: int,
    payload: ProjetUpdate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "PROJET_GERER")

    service = ProjetService(db)
    audit_service = AuditService(db)

    projet_existant = service.obtenir_projet(projet_id)
    if not projet_existant:
        raise HTTPException(status_code=404, detail=f"Projet #{projet_id} introuvable")
    _verifier_isolation(projet_existant.organisation_id, current_user)

    old_values = {
        "nom": projet_existant.nom,
        "bailleur": projet_existant.bailleur,
        "budget_annuel": float(projet_existant.budget_annuel or 0),
        "est_actif": projet_existant.est_actif,
    }

    data = payload.model_dump(exclude_unset=True)

    try:
        projet = service.mettre_a_jour(projet_id, data, user_id=None)
        db.commit()

        audit_service.log_update(
            user_id=current_user.id,
            table_name="projets",
            record_id=projet.id,
            old_values=old_values,
            new_values={
                "nom": projet.nom,
                "bailleur": projet.bailleur,
                "budget_annuel": float(projet.budget_annuel or 0),
                "est_actif": projet.est_actif,
            },
            request=request,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur modification projet : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return projet


# ============================================================================
# ROUTE 5 — DELETE /projets/{projet_id}
# ============================================================================

@router.delete(
    "/{projet_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Désactiver un projet",
)
def desactiver_projet(
    projet_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "PROJET_GERER")

    service = ProjetService(db)
    audit_service = AuditService(db)

    projet = service.obtenir_projet(projet_id)
    if not projet:
        raise HTTPException(status_code=404, detail=f"Projet #{projet_id} introuvable")
    _verifier_isolation(projet.organisation_id, current_user)

    code = projet.code

    try:
        service.desactiver(projet_id, user_id=None)
        db.commit()

        audit_service.log_action(
            user_id=current_user.id,
            table_name="projets",
            record_id=projet_id,
            action="DESACTIVATION",
            nouvelles_valeurs={"est_actif": False, "code": code},
            request=request,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur désactivation projet : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return None


# ============================================================================
# ROUTE 6 — GET /projets/{projet_id}/budget
# ============================================================================

@router.get(
    "/{projet_id}/budget",
    summary="Résumé budgétaire d'un projet",
)
def resume_budgetaire(
    projet_id: int,
    exercice: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "PROJET_VOIR")

    service = ProjetService(db)
    projet = service.obtenir_projet(projet_id)

    if not projet:
        raise HTTPException(status_code=404, detail=f"Projet #{projet_id} introuvable")

    _verifier_isolation(projet.organisation_id, current_user)

    if exercice is None:
        exercice = datetime.utcnow().year

    try:
        return service.get_resume_budgetaire(projet_id, exercice=exercice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))