# -*- coding: utf-8 -*-
"""
Endpoints CRUD pour la gestion des utilisateurs
Protection RBAC : Seul ADMIN peut créer/modifier/supprimer
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
    UtilisateurProfilUpdate
)
from ...services.auth_service import AuthService
from ...services.audit_service import AuditService
from ...api.dependencies import get_current_user, is_admin
from ...models.utilisateur import Utilisateur as UtilisateurModel
from ...core.security import get_password_hash, verify_password
from ...utils.search import ilike_pattern
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/utilisateurs", tags=["Utilisateurs"])


# =============================================================================
# READ - Lire les utilisateurs
# =============================================================================

@router.get("/", response_model=UtilisateurListResponse)
def list_utilisateurs(
    skip: int = Query(0, ge=0, description="Offset pour pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Limite de résultats"),
    actif: Optional[bool] = Query(None, description="Filtrer par statut actif"),
    recherche: Optional[str] = Query(None, description="Recherche sur nom/email/téléphone"),
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user)
) -> Any:
    """
    Liste tous les utilisateurs avec pagination et filtres.
    
    🔐 Accès : ADMIN uniquement
    """
    # Vérification RBAC
    if not current_user.has_role("ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs"
        )
    
    # Requête de base
    query = db.query(UtilisateurModel)
    
    # Filtres
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
    
    # Formatage de la réponse
    return UtilisateurListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[
            UtilisateurResponse(
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
                last_login=u.last_login
            )
            for u in items
        ]
    )


@router.get("/{user_id}", response_model=UtilisateurResponse)
def get_utilisateur(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user)
) -> Any:
    """
    Récupère les détails d'un utilisateur par son ID.
    
    🔐 Accès : ADMIN ou l'utilisateur lui-même
    """
    # Vérification RBAC
    if not current_user.has_role("ADMIN") and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez voir que votre propre profil"
        )
    
    # Recherche
    user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    return UtilisateurResponse(
        id=user.id,
        email=user.email,
        nom=user.nom,
        post_nom=user.post_nom,
        prenom=user.prenom,
        telephone=user.telephone,
        est_actif=user.est_actif,
        role_id=user.role_id,
        role_nom=user.role.nom if user.role else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login
    )


# =============================================================================
# CREATE - Ajouter un utilisateur
# =============================================================================

@router.post("/", response_model=UtilisateurResponse, status_code=status.HTTP_201_CREATED)
def create_utilisateur(
    utilisateur: UtilisateurCreate,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(is_admin)
) -> Any:
    """
    Crée un nouvel utilisateur.
    
    🔐 Accès : ADMIN uniquement
    
    - Le mot de passe est automatiquement hashé
    - L'email doit être unique
    - Le rôle doit exister en base
    """
    audit_service = AuditService(db)
    
    # Vérifier unicité email
    existing = db.query(UtilisateurModel).filter(
        UtilisateurModel.email == utilisateur.email
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà"
        )
    
    # Vérifier que le rôle existe
    from ...models.role import Role
    role = db.query(Role).filter(Role.id_role == utilisateur.role_id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle avec ID {utilisateur.role_id} non trouvé"
        )
    
    # Calculer le prochain ID
    next_id = UtilisateurModel.get_next_id(db)
    
    # Hasher le mot de passe
    hashed_password = get_password_hash(utilisateur.mot_de_passe)
    
    # Créer l'utilisateur
    new_user = UtilisateurModel(
        id=next_id,
        email=utilisateur.email,
        nom=utilisateur.nom,
        post_nom=utilisateur.post_nom,
        prenom=utilisateur.prenom,
        telephone=utilisateur.telephone,
        mot_de_passe=hashed_password,
        est_actif=True,
        role_id=utilisateur.role_id
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
            "role_id": new_user.role_id
        }
    )
    
    logger.info(f"Utilisateur créé : {new_user.email} par {current_user.email}")
    
    return UtilisateurResponse(
        id=new_user.id,
        email=new_user.email,
        nom=new_user.nom,
        post_nom=new_user.post_nom,
        prenom=new_user.prenom,
        telephone=new_user.telephone,
        est_actif=new_user.est_actif,
        role_id=new_user.role_id,
        role_nom=role.nom,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at,
        last_login=new_user.last_login
    )


# =============================================================================
# UPDATE - Modifier un utilisateur
# =============================================================================

@router.put("/{user_id}", response_model=UtilisateurResponse)
def update_utilisateur(
    user_id: int,
    utilisateur: UtilisateurUpdate,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user)
) -> Any:
    """
    Met à jour un utilisateur existant.
    
    🔐 Accès : ADMIN (tous champs) ou utilisateur lui-même (profil uniquement)
    """
    audit_service = AuditService(db)
    
    # Vérification RBAC
    if not current_user.has_role("ADMIN") and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que votre propre profil"
        )
    
    # Recherche
    db_user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Stocker anciennes valeurs pour audit
    anciennes_valeurs = {
        "email": db_user.email,
        "nom": db_user.nom,
        "prenom": db_user.prenom,
        "est_actif": db_user.est_actif
    }
    
    # Mise à jour des champs (seulement ceux fournis)
    update_data = utilisateur.model_dump(exclude_unset=True)
    
    # Un utilisateur normal ne peut pas changer son rôle ou son statut
    if not current_user.has_role("ADMIN"):
        update_data.pop("role_id", None)
        update_data.pop("est_actif", None)
    
    # Gestion du mot de passe
    if "mot_de_passe" in update_data and update_data["mot_de_passe"]:
        update_data["mot_de_passe"] = get_password_hash(update_data["mot_de_passe"])
    
    # Appliquer les mises à jour
    for field, value in update_data.items():
        if value is not None:
            setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    
    # Audit
    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=user_id,
        action="UPDATE",
        anciennes_valeurs=anciennes_valeurs,
        nouvelles_valeurs={k: v for k, v in update_data.items() if k != "mot_de_passe"}
    )
    
    logger.info(f"Utilisateur modifié : {db_user.email} par {current_user.email}")
    
    return UtilisateurResponse(
        id=db_user.id,
        email=db_user.email,
        nom=db_user.nom,
        post_nom=db_user.post_nom,
        prenom=db_user.prenom,
        telephone=db_user.telephone,
        est_actif=db_user.est_actif,
        role_id=db_user.role_id,
        role_nom=db_user.role.nom if db_user.role else None,
        created_at=db_user.created_at,
        updated_at=db_user.updated_at,
        last_login=db_user.last_login
    )


@router.patch("/{user_id}/profil", response_model=UtilisateurResponse)
def update_profil(
    user_id: int,
    profil: UtilisateurProfilUpdate,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(get_current_user)
) -> Any:
    """
    Permet à un utilisateur de mettre à jour son propre profil.
    
    🔐 Accès : Utilisateur connecté uniquement (pour son propre compte)
    """
    # Vérification : on ne peut modifier que son propre profil
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que votre propre profil"
        )
    
    # Gestion du changement de mot de passe
    if profil.ancien_mot_de_passe and profil.nouveau_mot_de_passe:
        if not verify_password(profil.ancien_mot_de_passe, current_user.mot_de_passe):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'ancien mot de passe est incorrect"
            )
        current_user.mot_de_passe = get_password_hash(profil.nouveau_mot_de_passe)
    
    # Mise à jour des autres champs
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
    
    logger.info(f"Profil mis à jour : {current_user.email}")
    
    return UtilisateurResponse(
        id=current_user.id,
        email=current_user.email,
        nom=current_user.nom,
        post_nom=current_user.post_nom,
        prenom=current_user.prenom,
        telephone=current_user.telephone,
        est_actif=current_user.est_actif,
        role_id=current_user.role_id,
        role_nom=current_user.role.nom if current_user.role else None,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        last_login=current_user.last_login
    )


# =============================================================================
# DELETE - Supprimer un utilisateur
# =============================================================================

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_utilisateur(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(is_admin)
) -> None:
    """
    Supprime définitivement un utilisateur.
    
    🔐 Accès : ADMIN uniquement
    
    ⚠️ Action irréversible - utilise une suppression physique
    """
    audit_service = AuditService(db)
    
    # Empêcher la suppression de son propre compte
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte"
        )
    
    # Recherche
    db_user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Stocker info pour audit avant suppression
    user_info = {
        "id": db_user.id,
        "email": db_user.email,
        "nom": db_user.nom
    }
    
    # Audit avant suppression
    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=user_id,
        action="DELETE",
        anciennes_valeurs=user_info,
        nouvelles_valeurs={"statut": "supprimé"}
    )
    
    # Suppression
    db.delete(db_user)
    db.commit()
    
    logger.info(f"Utilisateur supprimé : {user_info['email']} par {current_user.email}")


@router.patch("/{user_id}/toggle-actif", response_model=UtilisateurResponse)
def toggle_utilisateur_actif(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UtilisateurModel = Depends(is_admin)
) -> Any:
    """
    Active ou désactive un utilisateur (soft delete).
    
    🔐 Accès : ADMIN uniquement
    
    Plus sûr que la suppression : l'utilisateur ne peut plus se connecter
    mais ses données historiques sont conservées.
    """
    audit_service = AuditService(db)
    
    # Recherche
    db_user = db.query(UtilisateurModel).filter(UtilisateurModel.id == user_id).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Empêcher de désactiver son propre compte
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte"
        )
    
    # Inverser le statut
    ancien_statut = db_user.est_actif
    db_user.est_actif = not db_user.est_actif
    
    db.commit()
    db.refresh(db_user)
    
    # Audit
    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=user_id,
        action="TOGGLE_ACTIF",
        anciennes_valeurs={"est_actif": ancien_statut},
        nouvelles_valeurs={"est_actif": db_user.est_actif}
    )
    
    action = "activé" if db_user.est_actif else "désactivé"
    logger.info(f"Utilisateur {action} : {db_user.email} par {current_user.email}")
    
    return UtilisateurResponse(
        id=db_user.id,
        email=db_user.email,
        nom=db_user.nom,
        post_nom=db_user.post_nom,
        prenom=db_user.prenom,
        telephone=db_user.telephone,
        est_actif=db_user.est_actif,
        role_id=db_user.role_id,
        role_nom=db_user.role.nom if db_user.role else None,
        created_at=db_user.created_at,
        updated_at=db_user.updated_at,
        last_login=db_user.last_login
    )