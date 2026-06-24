# -*- coding: utf-8 -*-
"""
Schémas Pydantic pour la validation des données utilisateur
"""
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
import re


class UtilisateurBase(BaseModel):
    """Champs de base partagés pour création et mise à jour"""
    email: EmailStr
    nom: str
    post_nom: Optional[str] = None
    prenom: str
    telephone: Optional[str] = None

    


class UtilisateurCreate(UtilisateurBase):
    """Schéma pour la création d'un nouvel utilisateur"""
    mot_de_passe: str
    role_id: int  # ID du rôle à assigner (FK vers roles.id_role)
    
    @field_validator('mot_de_passe')
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validation de la complexité du mot de passe"""
        if len(v) < 6:
            raise ValueError("Le mot de passe doit contenir au moins 6 caractères")
        if not re.search(r'[A-Za-z]', v):
            raise ValueError("Le mot de passe doit contenir au moins une lettre")
        if not re.search(r'\d', v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


class UtilisateurUpdate(BaseModel):
    """Schéma pour la mise à jour d'un utilisateur (tous champs optionnels)"""
    email: Optional[EmailStr] = None
    nom: Optional[str] = None
    post_nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    mot_de_passe: Optional[str] = None
    est_actif: Optional[bool] = None
    role_id: Optional[int] = None
    
    @field_validator('mot_de_passe')
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validation de la complexité du mot de passe (si fourni)"""
        if v and len(v) < 6:
            raise ValueError("Le mot de passe doit contenir au moins 6 caractères")
        return v


class UtilisateurResponse(UtilisateurBase):
    """Schéma de réponse pour un utilisateur (sans données sensibles)"""
    id: int
    est_actif: bool
    role_id: int
    role_nom: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class UtilisateurListResponse(BaseModel):
    """Schéma pour la liste paginée d'utilisateurs"""
    total: int
    skip: int
    limit: int
    items: List[UtilisateurResponse]


class UtilisateurProfilUpdate(BaseModel):
    """Schéma pour qu'un utilisateur mette à jour son propre profil"""
    nom: Optional[str] = None
    post_nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    ancien_mot_de_passe: Optional[str] = None
    nouveau_mot_de_passe: Optional[str] = None
    
    @field_validator('nouveau_mot_de_passe')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if v and len(v) < 6:
            raise ValueError("Le mot de passe doit contenir au moins 6 caractères")
        return v
    