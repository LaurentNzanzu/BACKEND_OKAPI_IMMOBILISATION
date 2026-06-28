# -*- coding: utf-8 -*-
"""
Dépendances FastAPI pour l'authentification et la gestion des rôles
"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional, List

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.utilisateur import Utilisateur
from ..core.enums import RoleEnum
import logging

logger = logging.getLogger(__name__)

# Configuration OAuth2 pour l'extraction du token depuis le header Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[Utilisateur]:
    """
    Dépendance pour récupérer l'utilisateur si authentifié, sinon None.
    Utile pour les endpoints publics avec fonctionnalités supplémentaires pour les connectés.
    """
    try:
        return get_current_user(request, db, token)
    except HTTPException:
        return None


def require_role(allowed_roles: List[RoleEnum]):
    """
    Factory pour créer un décorateur de vérification de rôle.
    
    Args:
        allowed_roles: Liste des rôles autorisés à accéder à l'endpoint
        
    Returns:
        Fonction décorateur à utiliser avec Depends()
    """
    def role_checker(
        current_user: Utilisateur = Depends(get_current_user)
    ) -> Utilisateur:
        user_roles = [role.nom for role in current_user.roles]
        
        # Vérifier si l'utilisateur a l'un des rôles autorisés
        if not any(role.value in user_roles for role in allowed_roles):
            logger.warning(
                f"Accès refusé : utilisateur {current_user.email} "
                f"(rôles: {user_roles}) tente d'accéder à une ressource "
                f"nécessitant l'un des rôles : {[r.value for r in allowed_roles]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès réservé aux rôles : {[r.value for r in allowed_roles]}"
            )
        
        return current_user
    
    return role_checker


# === Décorateurs prêts à l'emploi par rôle ===

def is_admin(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
    """Vérifie que l'utilisateur a le rôle ADMIN"""
    if not current_user.has_role("ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs"
        )
    return current_user


def is_dg(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
    """Vérifie que l'utilisateur a le rôle DG ou ADMIN"""
    if not (current_user.has_role("DG") or current_user.has_role("ADMIN")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au Directeur Général"
        )
    return current_user


def is_comptable(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
    """Vérifie que l'utilisateur a le rôle COMPTABLE ou ADMIN"""
    if not (current_user.has_role("COMPTABLE") or current_user.has_role("ADMIN")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au service comptable"
        )
    return current_user


def is_technicien(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
    """Vérifie que l'utilisateur a le rôle TECHNICIEN ou ADMIN"""
    if not (current_user.has_role("TECHNICIEN") or current_user.has_role("ADMIN")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux techniciens"
        )
    return current_user


def require_any_roles(allowed_roles: List[str]):
    """Factory : l'utilisateur doit avoir l'un des rôles listés (ADMIN toujours autorisé)."""
    normalized = [r.upper() for r in allowed_roles]

    def role_checker(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
        if current_user.has_role("ADMIN"):
            return current_user
        user_role = current_user.role.nom.upper() if current_user.role else ""
        if user_role not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès réservé aux rôles : {', '.join(normalized)}",
            )
        return current_user

    return role_checker


# Rôles autorisés à consulter les immobilisations / sous-types
BIENS_VIEW_ROLES = ["ADMIN", "DG", "COMPTABLE", "TECHNICIEN", "CAISSE", "MAGASINIER", "GESTIONNAIRE"]


def deny_comptable_pieces_access(
    current_user: Utilisateur = Depends(get_current_user),
) -> Utilisateur:
    """Bloque l'accès au module pièces détachées pour le rôle Comptable."""
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role == "COMPTABLE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes",
        )
    return current_user


def is_caisse(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
    """Vérifie que l'utilisateur a le rôle CAISSE ou ADMIN"""
    if not (current_user.has_role("CAISSE") or current_user.has_role("ADMIN")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au service caisse"
        )
    return current_user