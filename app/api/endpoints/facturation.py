# backend/app/api/endpoints/facturation.py
"""
Endpoints de facturation SaaS.
Sprint 0 — Fondations multi-tenant OKAPI Flotte

Gère la génération, la consultation et le paiement des factures
d'abonnement. Utilise le schéma `AbonnementFacturation` existant.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.abonnement_facturation import (
    AbonnementFacturationResponse,
)
from ...services.facturation_service import FacturationService
from ...services.permission_service import PermissionService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/facturation", tags=["Facturation"])


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
    if current_user.organisation_id is None:
        return
    if organisation_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : cette ressource appartient à une autre organisation",
        )


# ============================================================================
# ROUTE 1 — GET /facturation
# ============================================================================

@router.get(
    "/",
    response_model=List[AbonnementFacturationResponse],
    summary="Lister les factures",
    description="Liste les factures avec filtres. Un utilisateur normal ne voit que celles de son organisation.",
)
def lister_factures(
    organisation_id: Optional[int] = Query(None, description="Filtrer par organisation (ADMIN plateforme uniquement)"),
    statut: Optional[str] = Query(None, description="Filtrer par statut (EN_ATTENTE, PAYE, RETARD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "FACTURATION_VOIR")

    # Isolation : si l'utilisateur a une organisation, forcer le filtre
    if current_user.organisation_id is not None:
        organisation_id = current_user.organisation_id
    elif organisation_id is not None:
        # ADMIN plateforme avec filtre → OK
        pass
    # Sinon ADMIN plateforme sans filtre → voit tout

    service = FacturationService(db)
    return service.lister_factures(
        organisation_id=organisation_id,
        statut=statut,
        skip=skip,
        limit=limit,
    )


# ============================================================================
# ROUTE 2 — POST /facturation/generer
# ============================================================================

@router.post(
    "/generer",
    response_model=AbonnementFacturationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Générer une facture",
    description="Génère manuellement une facture pour une organisation.",
)
def generer_facture(
    payload: dict = Body(
        ...,
        example={
            "organisation_id": 1,
            "periode": "2026-09",
            "montant": 99.0,
        },
    ),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "FACTURATION_GERER")

    org_id = payload.get("organisation_id")
    periode = payload.get("periode")
    montant = payload.get("montant")

    if not org_id:
        raise HTTPException(status_code=400, detail="organisation_id est obligatoire")
    if not periode:
        raise HTTPException(status_code=400, detail="periode est obligatoire (format YYYY-MM)")

    _verifier_isolation(int(org_id), current_user)

    service = FacturationService(db)
    audit_service = AuditService(db)

    try:
        facture = service.generer_facture(
            organisation_id=int(org_id),
            periode=periode,
            montant=float(montant) if montant is not None else None,
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
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur génération facture : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return facture


# ============================================================================
# ROUTE 3 — POST /facturation/{facture_id}/paiement
# ============================================================================

@router.post(
    "/{facture_id}/paiement",
    response_model=AbonnementFacturationResponse,
    summary="Enregistrer un paiement",
    description="Marque une facture comme payée.",
)
def enregistrer_paiement(
    facture_id: int,
    payload: dict = Body(default={}, example={"date_paiement": None, "montant": None}),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "FACTURATION_GERER")

    service = FacturationService(db)
    audit_service = AuditService(db)

    facture = service.obtenir_facture(facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail=f"Facture #{facture_id} introuvable")

    _verifier_isolation(facture.organisation_id, current_user)

    date_paiement = None
    if payload and payload.get("date_paiement"):
        try:
            date_paiement = datetime.fromisoformat(payload["date_paiement"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Format de date invalide (ISO 8601 requis)")

    try:
        facture = service.enregistrer_paiement(
            facture_id=facture_id,
            date_paiement=date_paiement,
            user_id=None,
        )
        db.commit()

        audit_service.log_action(
            user_id=current_user.id,
            table_name="abonnements_facturation",
            record_id=facture.id,
            action="PAIEMENT_ENREGISTRE",
            nouvelles_valeurs={
                "facture_id": facture.id,
                "montant": float(facture.montant),
                "date_paiement": facture.date_paiement.isoformat() if facture.date_paiement else None,
            },
            request=request,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur enregistrement paiement : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")

    return facture


# ============================================================================
# ROUTE 4 — GET /facturation/{facture_id}/pdf
# ============================================================================

@router.get(
    "/{facture_id}/pdf",
    summary="Exporter une facture en PDF",
    description="Retourne les données structurées d'une facture. Le PDF réel sera implémenté au Sprint 5+.",
)
def exporter_facture_pdf(
    facture_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    _verifier_permission(db, current_user, "FACTURATION_VOIR")

    service = FacturationService(db)

    facture = service.obtenir_facture(facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail=f"Facture #{facture_id} introuvable")

    _verifier_isolation(facture.organisation_id, current_user)

    try:
        data = service.exporter_facture_pdf(facture_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "PDF à venir Sprint 5+",
        "data": data,
    }