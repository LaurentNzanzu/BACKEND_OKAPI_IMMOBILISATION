# -*- coding: utf-8 -*-
"""
Service d'authentification : logique métier pour la gestion des utilisateurs et tokens
"""
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from fastapi import HTTPException, status

from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token
)
from ..core.enums import ActionAuditEnum
from .audit_service import AuditService
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """Service centralisé pour toutes les opérations d'authentification"""
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[Utilisateur]:
        """
        Authentifie un utilisateur avec son email et mot de passe.
        
        Args:
            db: Session SQLAlchemy
            email: Email de l'utilisateur
            password: Mot de passe en clair
            
        Returns:
            Utilisateur si authentifié, None sinon
        """
        try:
            # Rechercher l'utilisateur par email
            user = db.query(Utilisateur).filter(Utilisateur.email == email).first()
            
            if not user:
                logger.warning(f"Tentative de connexion avec email inconnu : {email}")
                return None
            
            if not user.est_actif:
                logger.warning(f"Tentative de connexion avec compte désactivé : {email}")
                return None
            
            # Vérifier le mot de passe
            if not verify_password(password, user.mot_de_passe):
                logger.warning(f"Mot de passe incorrect pour : {email}")
                return None
            
            logger.info(f"Authentification réussie pour : {email}")
            return user
            
        except Exception as e:
            logger.error(f"Erreur lors de l'authentification : {e}")
            raise
    
    @staticmethod
    def create_tokens(user_id: int) -> dict:
        """
        Génère les tokens d'accès et de rafraîchissement pour un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur authentifié
            
        Returns:
            dict: Contenant access_token, refresh_token et metadata
        """
        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 1800  # 30 minutes
        }
    
    @staticmethod
    def update_last_login(db: Session, user: Utilisateur, audit_service: AuditService):
        """
        Met à jour la date de dernière connexion et journalise l'action.
        
        Args:
            db: Session SQLAlchemy
            user: Utilisateur connecté
            audit_service: Service d'audit pour la journalisation
        """
        old_login = user.last_login
        user.last_login = datetime.utcnow()
        
        db.add(user)
        db.commit()
        
        # Journaliser la connexion dans l'audit
        audit_service.log_action(
            #db=db,
            user_id=user.id,
            table_name="utilisateurs",
            record_id=user.id,
            action=ActionAuditEnum.LOGIN.value,
            anciennes_valeurs={"last_login": str(old_login) if old_login else None},
            nouvelles_valeurs={"last_login": str(user.last_login)}
        )
        
        logger.info(f"Dernière connexion mise à jour pour l'utilisateur {user.id}")
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[Utilisateur]:
        """Recherche un utilisateur par son email"""
        return db.query(Utilisateur).filter(Utilisateur.email == email).first()
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[Utilisateur]:
        """Recherche un utilisateur par son ID"""
        return db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
    
      
    @staticmethod
    def get_user_roles(db: Session, user: Utilisateur) -> List[str]:
        """
        Retourne les rôles d'un utilisateur sous forme de liste.
        Garantit toujours le retour d'une liste, jamais None.
        """
        try:
            if user and user.role:
                # ✅ Supprime les espaces, met en majuscules, retourne une liste
                role_name = user.role.nom.strip().upper()
                logger.info(f"✅ Rôle trouvé pour {user.email}: {role_name}")
                return [role_name]
            else:
                logger.warning(f"⚠️ Aucun rôle trouvé pour l'utilisateur {user.email if user else 'Unknown'}")
                return []  # ✅ Toujours retourner une liste vide, pas None
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des rôles: {e}")
            return []  # ✅ Toujours retourner une liste en cas d'erreur
        
    @staticmethod
    def refresh_access_token(refresh_token: str, db: Session) -> dict:
        """
        Rafraîchit un token d'accès à partir d'un refresh token valide.
        
        Args:
            refresh_token: Refresh token JWT
            db: Session SQLAlchemy
            
        Returns:
            dict: Nouveaux tokens
            
        Raises:
            HTTPException: Si le token est invalide ou expiré
        """
        try:
            # Décoder et vérifier le refresh token
            payload = decode_token(refresh_token)
            
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Type de token invalide"
                )
            
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token invalide"
                )
            
            # Vérifier que l'utilisateur existe et est actif
            user = AuthService.get_user_by_id(db, int(user_id))
            if not user or not user.est_actif:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Utilisateur non trouvé ou désactivé"
                )
            
            # Générer de nouveaux tokens
            return AuthService.create_tokens(user.id)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur lors du rafraîchissement du token : {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de rafraîchissement invalide ou expiré"
            )
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash un mot de passe pour le stockage sécurisé"""
        return get_password_hash(password)
    
    @staticmethod
    def create_user_with_hashed_password(
        db: Session, 
        email: str, 
        password: str, 
        nom: str, 
        prenom: str,
        role_id: int,  # ⚠️ Utilise role_id (FK vers roles.id_role)
        post_nom: Optional[str] = None,
        telephone: Optional[str] = None
    ) -> Utilisateur:
        """
        Crée un nouvel utilisateur avec mot de passe hashé.
        Utilise la méthode get_next_id() pour la gestion manuelle des IDs.
        """
        # Calculer le prochain ID avec la méthode personnalisée
        next_id = Utilisateur.get_next_id(db)
        
        # Hasher le mot de passe
        hashed_password = get_password_hash(password)
        
        # Créer l'utilisateur
        new_user = Utilisateur(
            id=next_id,
            email=email,
            nom=nom,
            post_nom=post_nom,
            prenom=prenom,
            telephone=telephone,
            mot_de_passe=hashed_password,
            est_actif=True,
            role_id=role_id  # ⚠️ Clé étrangère vers roles.id_role
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"Utilisateur créé avec succès - ID: {next_id}, Email: {email}")
        return new_user