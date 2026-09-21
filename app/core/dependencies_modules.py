# backend/app/core/dependencies_modules.py
# -*- coding: utf-8 -*-
"""
Dépendances FastAPI pour la vérification des modules SaaS activés.
Phase 1 — Fondations SaaS multi-tenant OKAPI Flotte

Fonction principale :
- require_module(module_code) : vérifie que le module est actif pour l'ONG
- require_modules(*codes)     : vérifie plusieurs modules

Règles :
- ADMIN plateforme (organisation_id NULL) → accès total (bypass)
- Sinon : l'organisation doit avoir ce module dans parametres_json.modules_actifs
- Si l'organisation n'est pas ACTIF → 403
- Si module inconnu du registre → ValueError au démarrage (erreur dev)
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from .database import get_db
from .security import get_current_user
from .module_registry import module_existe
from ..models.utilisateur import Utilisateur
from ..models.organisation import Organisation, StatutOrganisation

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS INTERNES
# ============================================================================

def _get_user_organisation_id(user: Utilisateur):
    """
    Extrait l'organisation_id d'un utilisateur de manière défensive.

    ⚠️ NOTE : get_current_user() peut retourner un utilisateur reconstruit
    depuis le cache sans organisation_id. On utilise getattr() pour éviter
    une AttributeError. Voir security.py (à corriger en Phase 3).
    """
    if not user:
        return None
    return getattr(user, "organisation_id", None)


def _get_role_nom(user: Utilisateur) -> str:
    """Extrait le nom du rôle (normalisé en uppercase)."""
    if not user:
        return ""
    role = getattr(user, "role", None)
    if not role:
        return ""
    return (getattr(role, "nom", "") or "").strip().upper()


def _is_platform_admin(user: Utilisateur) -> bool:
    """Un ADMIN plateforme = organisation_id NULL + rôle ADMIN."""
    if not user:
        return False
    if _get_user_organisation_id(user) is not None:
        return False
    return _get_role_nom(user) == "ADMIN"


def _get_modules_actifs(organisation: Organisation) -> set:
    """Retourne l'ensemble normalisé des modules actifs d'une organisation."""
    if not organisation:
        return set()
    parametres = organisation.parametres_json or {}
    modules = parametres.get("modules_actifs", []) or []
    return {str(m).strip().upper() for m in modules if m}


# ============================================================================
# DÉPENDANCE PUBLIQUE
# ============================================================================

def require_module(module_code: str):
    """
    Factory de dépendance FastAPI qui vérifie que le module est actif
    pour l'organisation de l'utilisateur connecté.

    Usage :
        router = APIRouter(
            prefix="/missions",
            tags=["Missions"],
            dependencies=[Depends(require_module("MISSION"))],
        )

    Args:
        module_code: Code du module (doit exister dans MODULES_DISPONIBLES)

    Raises:
        ValueError: au moment de l'enregistrement du routeur si le code est invalide
        HTTPException 401: si non authentifié
        HTTPException 403: si module non actif ou organisation inactive
    """
    if not module_existe(module_code):
        raise ValueError(
            f"Module '{module_code}' inconnu du registre. "
            f"Utilisez un code valide de ModuleCode."
        )

    code_normalized = str(module_code).strip().upper()

    def dependency(
        current_user: Utilisateur = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> bool:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise",
            )

        # ADMIN plateforme → accès total (bypass)
        if _is_platform_admin(current_user):
            return True

        org_id = _get_user_organisation_id(current_user)
        if org_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Aucune organisation associée à cet utilisateur",
            )

        organisation = (
            db.query(Organisation)
            .filter(Organisation.id == org_id)
            .first()
        )
        if not organisation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organisation introuvable",
            )

        # Vérifier que l'organisation est active
        if organisation.statut != StatutOrganisation.ACTIF:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Organisation '{organisation.code}' non active "
                    f"(statut: {organisation.statut.value})"
                ),
            )

        # Vérifier le module
        modules_actifs = _get_modules_actifs(organisation)

        if code_normalized not in modules_actifs:
            logger.warning(
                f"Module '{code_normalized}' non actif pour organisation "
                f"#{org_id} ({organisation.code}). "
                f"Utilisateur #{getattr(current_user, 'id', '?')}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Le module '{code_normalized}' n'est pas activé "
                    f"pour votre organisation. Contactez votre administrateur."
                ),
            )

        return True

    return dependency


def require_modules(*module_codes: str, require_all: bool = True):
    """
    Vérifie plusieurs modules à la fois.

    Args:
        module_codes: Codes des modules à vérifier
        require_all: True → tous les modules doivent être actifs
                     False → au moins un doit être actif
    """
    if not module_codes:
        raise ValueError("Au moins un module doit être fourni")

    for code in module_codes:
        if not module_existe(code):
            raise ValueError(f"Module '{code}' inconnu du registre")

    codes_normalized = [str(c).strip().upper() for c in module_codes]

    def dependency(
        current_user: Utilisateur = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> bool:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise",
            )

        if _is_platform_admin(current_user):
            return True

        org_id = _get_user_organisation_id(current_user)
        if org_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Aucune organisation associée à cet utilisateur",
            )

        organisation = (
            db.query(Organisation).filter(Organisation.id == org_id).first()
        )
        if not organisation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organisation introuvable",
            )

        modules_actifs = _get_modules_actifs(organisation)

        if require_all:
            manquants = [c for c in codes_normalized if c not in modules_actifs]
            if manquants:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Modules non activés : {', '.join(manquants)}",
                )
        else:
            if not any(c in modules_actifs for c in codes_normalized):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Aucun des modules requis n'est activé : "
                        f"{', '.join(codes_normalized)}"
                    ),
                )

        return True

    return dependency


def get_user_modules(
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    """
    Helper de lecture : retourne la liste des modules actifs pour
    l'utilisateur connecté.

    - ADMIN plateforme → tous les modules disponibles
    - Utilisateur ONG → ses modules actifs
    - Utilisateur sans ONG → liste vide

    Usage :
        def mon_endpoint(modules: list = Depends(get_user_modules)):
            ...
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    if _is_platform_admin(current_user):
        from .module_registry import MODULES_DISPONIBLES
        return list(MODULES_DISPONIBLES.keys())

    org_id = _get_user_organisation_id(current_user)
    if org_id is None:
        return []

    organisation = (
        db.query(Organisation).filter(Organisation.id == org_id).first()
    )
    if not organisation:
        return []

    return list(_get_modules_actifs(organisation))