# backend/app/api/endpoints/abonnements.py
"""
Endpoints de gestion des abonnements SaaS.
Sprint 0 — Fondations multi-tenant OKAPI Flotte

Gère les abonnements des organisations : création, consultation,
renouvellement et suivi des quotas.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.abonnement_facturation import (
    AbonnementFacturationCreate,
    AbonnementFacturationResponse,
)
from ...services.facturation_service import FacturationService
from ...services.organisation_service import OrganisationService
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/abonnements", tags=["Abonnements"])


# ============================================================================
# HELPERS
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


def _verifier_isolation(organisation_id: int, current_user: Utilisateur) -> None:
    """Vérifie que l'utilisateur peut accéder aux données de cette organisation."""
    if current_user.organisation_id is None:
        # ADMIN plateforme → accès total
        return
    if organisation_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : cette ressource appartient à une autre organisation",
        )


# ============================================================================
# ROUTE 1 — POST /abonnements
# ============================================================================

@router.post(
    "/",
    response_model=AbonnementFacturationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un abonnement",
    description="Crée une facture d'abonnement pour une organisation.",
)
def creer_abonnement(
    payload: AbonnementFacturationCreate = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "ABONNEMENT_GERER")

    # Vérifier l'isolation
    _verifier_isolation(payload.organisation_id, current_user)

    service = FacturationService(db)
    audit_service = AuditService(db)

    try:
        facture = service.generer_facture(
            organisation_id=payload.organisation_id,
            periode=payload.periode,
            montant=float(payload.montant),
            date_echeance=payload.date_echeance,
            user_id=None,
        )
        db.commit()

        audit_service.log_create(
            user_id=current_user.id,
            table_name="abonnements_facturation",
            record_id=facture.id,
            new_values={
                "organisation_id": facture.organisation_id,
                "periode": facture.periode,
                "montant": float(facture.montant),
                "devise": facture.devise,
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création abonnement : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return facture


# ============================================================================
# ROUTE 2 — GET /abonnements/{organisation_id}
# ============================================================================

@router.get(
    "/{organisation_id}",
    summary="Vérifier l'abonnement actif d'une organisation",
    description="Retourne le statut d'abonnement et les informations associées.",
)
@router.get(
    "/{organisation_id}/",
    include_in_schema=False,
)
def verifier_abonnement(
    organisation_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "ABONNEMENT_VOIR")
    _verifier_isolation(organisation_id, current_user)

    org_service = OrganisationService(db)
    organisation = org_service.obtenir_organisation(organisation_id)
    if not organisation:
        raise HTTPException(
            status_code=404, detail=f"Organisation #{organisation_id} introuvable"
        )

    # Résumé de facturation
    fact_service = FacturationService(db)
    resume = fact_service.get_resume_facturation(organisation_id)

    return {
        "organisation_id": organisation.id,
        "organisation_code": organisation.code,
        "plan_abonnement": (
            organisation.plan_abonnement.value
            if organisation.plan_abonnement
            else None
        ),
        "statut_organisation": organisation.statut.value,
        "est_actif": organisation.est_actif,
        "date_debut": organisation.date_debut.isoformat() if organisation.date_debut else None,
        "date_fin": organisation.date_fin.isoformat() if organisation.date_fin else None,
        "facturation": resume,
    }


# ============================================================================
# ROUTE 3 — GET /abonnements/{organisation_id}/quotas
# ============================================================================

@router.get(
    "/{organisation_id}/quotas",
    summary="Résumé des quotas d'une organisation",
    description="Retourne l'utilisation et les quotas de véhicules, chauffeurs et missions.",
)
@router.get(
    "/{organisation_id}/quotas/",
    include_in_schema=False,
)
def quotas_organisation(
    organisation_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "ABONNEMENT_VOIR")
    _verifier_isolation(organisation_id, current_user)

    org_service = OrganisationService(db)
    try:
        return org_service.get_quota_summary(organisation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# ROUTE 4 — POST /abonnements/{organisation_id}/renouveler
# ============================================================================

@router.post(
    "/{organisation_id}/renouveler",
    response_model=AbonnementFacturationResponse,
    summary="Renouveler un abonnement",
    description="Génère une facture de renouvellement pour une durée donnée.",
)
@router.post(
    "/{organisation_id}/renouveler/",
    response_model=AbonnementFacturationResponse,
    include_in_schema=False,
)
def renouveler_abonnement(
    organisation_id: int,
    payload: dict = Body(..., example={"duree_mois": 12}),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "ABONNEMENT_GERER")
    _verifier_isolation(organisation_id, current_user)

    org_service = OrganisationService(db)
    organisation = org_service.obtenir_organisation(organisation_id)
    if not organisation:
        raise HTTPException(
            status_code=404, detail=f"Organisation #{organisation_id} introuvable"
        )

    duree_mois = int((payload or {}).get("duree_mois", 12))
    if duree_mois <= 0:
        raise HTTPException(
            status_code=400, detail="La durée en mois doit être > 0"
        )

    # Calculer la période au format YYYY-MM
    aujourd_hui = datetime.utcnow()
    periode = f"{aujourd_hui.year}-{aujourd_hui.month:02d}"
    date_echeance = (aujourd_hui + timedelta(days=30 * duree_mois)).date()

    fact_service = FacturationService(db)
    audit_service = AuditService(db)

    try:
        facture = fact_service.generer_facture(
            organisation_id=organisation_id,
            periode=periode,
            date_echeance=date_echeance,
            user_id=None,
        )
        db.commit()

        audit_service.log_action(
            user_id=current_user.id,
            table_name="abonnements_facturation",
            record_id=facture.id,
            action="RENOUVELLEMENT_ABONNEMENT",
            nouvelles_valeurs={
                "organisation_id": organisation_id,
                "periode": periode,
                "duree_mois": duree_mois,
                "montant": float(facture.montant),
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur renouvellement abonnement : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return facture