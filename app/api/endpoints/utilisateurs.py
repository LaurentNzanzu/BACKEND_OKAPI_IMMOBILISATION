# -*- coding: utf-8 -*-
"""
Endpoints CRUD pour la gestion des utilisateurs.
Phase 5 — Isolation stricte par ONG.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Any
from datetime import datetime

from ...core.database import get_db
from ...schemas.utilisateur import (
    UtilisateurCreate,
    UtilisateurUpdate,
    UtilisateurResponse,
    UtilisateurListResponse,
    UtilisateurProfilUpdate,
)
from ...services.auth_service import AuthService
from ...services.audit_service import AuditService
from ...api.dependencies import get_current_user, is_admin
from ...models.utilisateur import Utilisateur as UtilisateurModel
from ...models.role import Role
from ...core.security import get_password_hash, verify_password
from ...utils.search import ilike_pattern
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/utilisateurs", tags=["Utilisateurs"])


# ============================================================================
# ✅ HELPERS D'ISOLATION MULTI-TENANT
# ============================================================================

def _is_platform_admin(user: UtilisateurModel) -> bool:
    """
    ADMIN plateforme = organisation_id NULL + rôle ADMIN.
    C'est le SEUL qui peut voir tous les utilisateurs.
    """
    if not user:
        return False
    if user.organisation_id is not None:
        return False
    role_nom = (user.role.nom if user.role else "").strip().upper()
    return role_nom == "ADMIN"


def _apply_ong_filter(query, current_user: UtilisateurModel):
    """
    Applique le filtre organisation_id :
    - ADMIN plateforme → voit TOUT
    - Utilisateur ONG → voit UNIQUEMENT sa propre organisation
    """
    if _is_platform_admin(current_user):
        return query
    # Utilisateur ONG : filtre strict
    return query.filter(
        UtilisateurModel.organisation_id == current_user.organisation_id
    )


def _serialize(u: UtilisateurModel) -> UtilisateurResponse:
    """Sérialise un UtilisateurModel en UtilisateurResponse."""
    return UtilisateurResponse(
        id=u.id,
        email=u.email,
        nom=u.nom,
        post_nom=u.post_nom,
        prenom=u.prenom,
        telephone=u.telephone,
        est_actif=u.est_actif,
        role_id=u.role_id,
        role_nom=u.role.nom if u.role else None,
        created_at=u.created_at,
        updated_at=u.updated_at,
        last_login=u.last_login,
    )


# =============================================================================
# READ — Lister les utilisateurs
# =============================================================================

@router.get("/", response_model=UtilisateurListResponse)
@router.get("", response_model=UtilisateurListResponse, include_in_schema=False)
def list_utilisateurs(
    skip: int = Query(0, ge=0, description="Offset pour pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Limite de résultats"),
    actif: Optional[bool] = Query(None, description="Filtrer par statut actif"),
    recherche: Optional[str] = Query(None, description="Recherche sur nom/email/téléphone"),
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user),
) -> Any:
    """
    Liste les utilisateurs avec isolation multi-tenant :
    - ADMIN plateforme → voit TOUS les utilisateurs
    - ADMIN ONG → voit UNIQUEMENT ceux de sa propre organisation
    """
    # Vérification RBAC
    if not current_user.has_role("ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )

    # ✅ DIAGNOSTIC (retirez après validation)
    logger.info(
        f"[DIAG] list_utilisateurs | "
        f"user_id={current_user.id} "
        f"email={current_user.email} "
        f"org_id={current_user.organisation_id} "
        f"is_platform={_is_platform_admin(current_user)}"
    )

    # Requête de base
    query = db.query(UtilisateurModel)

    # ✅ ISOLATION MULTI-TENANT
    query = _apply_ong_filter(query, current_user)

    # Filtres additionnels
    if actif is not None:
        query = query.filter(UtilisateurModel.est_actif == actif)

    if recherche:
        search_term = ilike_pattern(recherche)
        if search_term:
            query = query.filter(
                (UtilisateurModel.nom.ilike(search_term))
                | (UtilisateurModel.prenom.ilike(search_term))
                | (UtilisateurModel.email.ilike(search_term))
                | (UtilisateurModel.telephone.ilike(search_term))
            )

    # Pagination
    total = query.count()
    items = query.offset(skip).limit(limit).all()

    return UtilisateurListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_serialize(u) for u in items],
    )


@router.get("/{user_id}", response_model=UtilisateurResponse)
@router.get("/{user_id}/", response_model=UtilisateurResponse, include_in_schema=False)
def get_utilisateur(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user),
) -> Any:
    """
    Récupère les détails d'un utilisateur.
    - ADMIN plateforme → peut voir n'importe qui
    - Utilisateur ONG → uniquement les users de son ONG
    """
    # Vérification RBAC
    if not current_user.has_role("ADMIN") and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez voir que votre propre profil",
        )

    # Recherche
    user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    # ✅ ISOLATION : un ADMIN ONG ne peut voir que sa propre ONG
    if not _is_platform_admin(current_user):
        if user.organisation_id != current_user.organisation_id and current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé : utilisateur d'une autre organisation",
            )

    return _serialize(user)


# =============================================================================
# CREATE — Ajouter un utilisateur
# =============================================================================

@router.post("/", response_model=UtilisateurResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=UtilisateurResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_utilisateur(
    utilisateur: UtilisateurCreate,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(is_admin),
) -> Any:
    """
    Crée un nouvel utilisateur.
    - ADMIN plateforme : peut créer dans n'importe quelle ONG
    - ADMIN ONG : ne peut créer que dans SA propre ONG
    """
    audit_service = AuditService(db)

    # Vérifier unicité email
    existing = db.query(UtilisateurModel).filter(
        UtilisateurModel.email == utilisateur.email
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà",
        )

    # Vérifier le rôle
    role = db.query(Role).filter(Role.id_role == utilisateur.role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle avec ID {utilisateur.role_id} non trouvé",
        )

    # ✅ ISOLATION : déterminer l'organisation cible
    if _is_platform_admin(current_user):
        # ADMIN plateforme : peut cibler n'importe quelle ONG
        target_org_id = getattr(utilisateur, "organisation_id", None)
    else:
        # ADMIN ONG : forcé sur sa propre ONG
        target_org_id = current_user.organisation_id

    next_id = UtilisateurModel.get_next_id(db)
    hashed_password = get_password_hash(utilisateur.mot_de_passe)

    new_user = UtilisateurModel(
        id=next_id,
        email=utilisateur.email,
        nom=utilisateur.nom,
        post_nom=utilisateur.post_nom,
        prenom=utilisateur.prenom,
        telephone=utilisateur.telephone,
        mot_de_passe=hashed_password,
        est_actif=True,
        role_id=utilisateur.role_id,
        organisation_id=target_org_id,
        doit_changer_mot_de_passe=False,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Audit
    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=new_user.id,
        action="CREATE",
        nouvelles_valeurs={
            "email": new_user.email,
            "nom": new_user.nom,
            "role_id": new_user.role_id,
            "organisation_id": new_user.organisation_id,
        },
    )

    logger.info(f"Utilisateur créé : {new_user.email} par {current_user.email}")
    return _serialize(new_user)


# =============================================================================
# UPDATE — Modifier un utilisateur
# =============================================================================

@router.put("/{user_id}", response_model=UtilisateurResponse)
@router.put("/{user_id}/", response_model=UtilisateurResponse, include_in_schema=False)
def update_utilisateur(
    user_id: int,
    utilisateur: UtilisateurUpdate,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user),
) -> Any:
    audit_service = AuditService(db)

    # Vérification RBAC
    if not current_user.has_role("ADMIN") and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que votre propre profil",
        )

    db_user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    # ✅ ISOLATION : ADMIN ONG ne peut modifier que sa propre ONG
    if not _is_platform_admin(current_user) and current_user.has_role("ADMIN"):
        if db_user.organisation_id != current_user.organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé : utilisateur d'une autre organisation",
            )

    # Stocker anciennes valeurs
    anciennes_valeurs = {
        "email": db_user.email,
        "nom": db_user.nom,
        "prenom": db_user.prenom,
        "est_actif": db_user.est_actif,
    }

    update_data = utilisateur.model_dump(exclude_unset=True)

    # Un utilisateur normal ne peut pas changer son rôle/statut
    if not current_user.has_role("ADMIN"):
        update_data.pop("role_id", None)
        update_data.pop("est_actif", None)

    # Gestion mot de passe
    if "mot_de_passe" in update_data and update_data["mot_de_passe"]:
        update_data["mot_de_passe"] = get_password_hash(update_data["mot_de_passe"])

    # Appliquer
    for field, value in update_data.items():
        if value is not None:
            setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)

    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=user_id,
        action="UPDATE",
        anciennes_valeurs=anciennes_valeurs,
        nouvelles_valeurs={k: v for k, v in update_data.items() if k != "mot_de_passe"},
    )

    return _serialize(db_user)


@router.patch("/{user_id}/profil", response_model=UtilisateurResponse)
@router.patch("/{user_id}/profil/", response_model=UtilisateurResponse, include_in_schema=False)
def update_profil(
    user_id: int,
    profil: UtilisateurProfilUpdate,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user),
) -> Any:
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que votre propre profil",
        )

    if profil.ancien_mot_de_passe and profil.nouveau_mot_de_passe:
        if not verify_password(profil.ancien_mot_de_passe, current_user.mot_de_passe):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'ancien mot de passe est incorrect",
            )
        current_user.mot_de_passe = get_password_hash(profil.nouveau_mot_de_passe)

    if profil.nom:
        current_user.nom = profil.nom
    if profil.post_nom:
        current_user.post_nom = profil.post_nom
    if profil.prenom:
        current_user.prenom = profil.prenom
    if profil.telephone:
        current_user.telephone = profil.telephone

    db.commit()
    db.refresh(current_user)

    return _serialize(current_user)


# =============================================================================
# DELETE — Supprimer un utilisateur
# =============================================================================

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{user_id}/", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def delete_utilisateur(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(is_admin),
) -> None:
    audit_service = AuditService(db)

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte",
        )

    db_user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    # ✅ ISOLATION
    if not _is_platform_admin(current_user):
        if db_user.organisation_id != current_user.organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé : utilisateur d'une autre organisation",
            )

    user_info = {
        "id": db_user.id,
        "email": db_user.email,
        "nom": db_user.nom,
    }

    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=user_id,
        action="DELETE",
        anciennes_valeurs=user_info,
        nouvelles_valeurs={"statut": "supprimé"},
    )

    db.delete(db_user)
    db.commit()


@router.patch("/{user_id}/toggle-actif", response_model=UtilisateurResponse)
@router.patch("/{user_id}/toggle-actif/", response_model=UtilisateurResponse, include_in_schema=False)
def toggle_utilisateur_actif(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(is_admin),
) -> Any:
    audit_service = AuditService(db)

    db_user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte",
        )

    # ✅ ISOLATION
    if not _is_platform_admin(current_user):
        if db_user.organisation_id != current_user.organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé : utilisateur d'une autre organisation",
            )

    ancien_statut = db_user.est_actif
    db_user.est_actif = not db_user.est_actif

    db.commit()
    db.refresh(db_user)

    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=user_id,
        action="TOGGLE_ACTIF",
        anciennes_valeurs={"est_actif": ancien_statut},
        nouvelles_valeurs={"est_actif": db_user.est_actif},
    )

    action = "activé" if db_user.est_actif else "désactivé"
    logger.info(f"Utilisateur {action} : {db_user.email} par {current_user.email}")

    return _serialize(db_user)