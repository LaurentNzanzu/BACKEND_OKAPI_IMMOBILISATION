from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from ...core.database import get_db
from ...core.security import get_current_user
from ...core.module_registry import (
    lister_tous_modules,
    get_module_info,
    get_modules_pour_plan,
    MODULES_PAR_PLAN,
    MODULES_DISPONIBLES,
)
from ...models.utilisateur import Utilisateur
from ...services.organisation_service import OrganisationService

router = APIRouter(prefix="/modules", tags=["Modules SaaS"])


def _verifier_admin_plateforme(current_user: Utilisateur) -> None:
    if current_user.organisation_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'ADMIN plateforme",
        )


# ============================================================================
# GET /modules — Liste tous les modules disponibles
# ============================================================================

@router.get(
    "/",
    summary="Lister les modules disponibles",
    description="Retourne le référentiel complet des 18 modules SaaS.",
)
@router.get("", include_in_schema=False)
def lister_modules(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
) -> List[Dict[str, str]]:
    _verifier_admin_plateforme(current_user)
    return lister_tous_modules()


# ============================================================================
# GET /modules/plans — Modules par plan
# ============================================================================

@router.get(
    "/plans",
    summary="Modules par plan d'abonnement",
    description="Retourne la cartographie BASIC / PRO / ENTERPRISE.",
)
@router.get("/plans/", include_in_schema=False)
def modules_par_plan(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
) -> Dict[str, Any]:
    _verifier_admin_plateforme(current_user)
    return {
        "plans": {
            plan: {
                "modules": modules,
                "total": len(modules),
            }
            for plan, modules in MODULES_PAR_PLAN.items()
        }
    }


# ============================================================================
# GET /modules/{module_code} — Détails d'un module
# ============================================================================

@router.get(
    "/{module_code}",
    summary="Détails d'un module",
    description="Retourne les métadonnées d'un module spécifique.",
)
@router.get("/{module_code}/", include_in_schema=False)
def obtenir_module(
    module_code: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
) -> Dict[str, str]:
    _verifier_admin_plateforme(current_user)

    module_code_up = module_code.strip().upper()
    if module_code_up not in MODULES_DISPONIBLES:
        raise HTTPException(
            status_code=404,
            detail=f"Module '{module_code}' inconnu",
        )

    info = get_module_info(module_code_up)
    return {"code": module_code_up, **(info or {})}