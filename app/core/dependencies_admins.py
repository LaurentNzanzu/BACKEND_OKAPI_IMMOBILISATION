# backend/app/core/dependencies_admins.py
# -*- coding: utf-8 -*-
"""
Dépendances FastAPI pour distinguer les 2 niveaux d'administration.
Phase 1 — Fondations SaaS multi-tenant OKAPI Flotte

Règles structurelles :
- ADMIN PLATEFORME = organisation_id IS NULL + role.nom == "ADMIN"
- ADMIN ONG        = organisation_id IS NOT NULL + role.nom == "ADMIN"
- Les autres rôles (DG, COMPTABLE, etc.) ne sont JAMAIS admin.
"""
from fastapi import Depends, HTTPException, status
import logging

from .security import get_current_user
from ..models.utilisateur import Utilisateur

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS INTERNES
# ============================================================================

def _get_role_nom(user: Utilisateur) -> str:
    """Extrait le nom du rôle (normalisé en uppercase)."""
    if not user:
        return ""
    role = getattr(user, "role", None)
    if not role:
        return ""
    return (getattr(role, "nom", "") or "").strip().upper()


def _get_organisation_id(user: Utilisateur):
    """Extrait l'organisation_id (défensif vis-à-vis du cache)."""
    if not user:
        return None
    return getattr(user, "organisation_id", None)


# ============================================================================
# DÉPENDANCES PUBLIQUES
# ============================================================================

def is_platform_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    """
    Vérifie que l'utilisateur est un ADMIN PLATEFORME.

    Un ADMIN plateforme :
    - A un rôle ADMIN
    - N'est rattaché à AUCUNE organisation (organisation_id IS NULL)

    Usage :
        @router.post(
            "/organisations/",
            dependencies=[Depends(is_platform_admin)],
        )
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    org_id = _get_organisation_id(current_user)
    role_nom = _get_role_nom(current_user)

    if org_id is not None:
        logger.warning(
            f"Accès refusé plateforme : utilisateur "
            f"#{getattr(current_user, 'id', '?')} appartient à organisation #{org_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'administrateur de la plateforme",
        )

    if role_nom != "ADMIN":
        logger.warning(
            f"Accès refusé plateforme : utilisateur "
            f"#{getattr(current_user, 'id', '?')} a le rôle '{role_nom}' (ADMIN requis)"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé à l'administrateur de la plateforme",
        )

    return current_user


def is_org_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    """
    Vérifie que l'utilisateur est un ADMIN d'une ONG.

    Un ADMIN ONG :
    - A un rôle ADMIN
    - Est rattaché à une organisation (organisation_id IS NOT NULL)

    Usage :
        @router.get(
            "/utilisateurs/",
            dependencies=[Depends(is_org_admin)],
        )
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    org_id = _get_organisation_id(current_user)
    role_nom = _get_role_nom(current_user)

    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs d'organisation",
        )

    if role_nom != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs d'organisation",
        )

    return current_user


def is_any_admin(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    """
    Accepte un ADMIN plateforme OU un ADMIN ONG.
    Utile pour les endpoints accessibles aux deux niveaux.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    role_nom = _get_role_nom(current_user)
    if role_nom != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )

    return current_user


def get_user_organisation_id(
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Helper : retourne l'organisation_id de l'utilisateur connecté.

    - None si ADMIN plateforme
    - Sinon l'ID entier de l'organisation

    Usage :
        def mon_endpoint(org_id = Depends(get_user_organisation_id)):
            if org_id is None:
                # mode admin plateforme
            else:
                # mode ONG
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )
    return _get_organisation_id(current_user)