from datetime import datetime, timedelta
from typing import Optional, Union, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session, joinedload
from .config import settings
from .cookies import ACCESS_COOKIE
from ..models.utilisateur import Utilisateur
from ..core.database import get_db
import logging

logger = logging.getLogger(__name__)

# Configuration OAuth2 pour extraire le token depuis le header Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Configuration du hachage des mots de passe (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# === Gestion des mots de passe ===

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si un mot de passe en clair correspond à un hash bcrypt."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Erreur vérification mot de passe : {e}")
        return False


def get_password_hash(password: str) -> str:
    """Génère un hash bcrypt sécurisé."""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Erreur hachage mot de passe : {e}")
        raise


# === Gestion des tokens JWT ===

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Crée un token d'accès JWT signé."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: Union[str, Any]) -> str:
    """Crée un refresh token JWT (durée de vie : 7 jours)."""
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Décode et vérifie un token JWT."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT expiré")
        raise JWTError("Token expiré")
    except jwt.JWTError as e:
        logger.error(f"Erreur décodage token JWT : {e}")
        raise JWTError(f"Token invalide : {str(e)}")


def get_token_subject(token: str) -> Optional[str]:
    """Extrait l'identifiant utilisateur depuis un token."""
    try:
        payload = decode_token(token)
        return payload.get("sub")
    except JWTError:
        return None


# === ✅ CORRIGÉ : Dépendance d'authentification pour FastAPI ===

from .redis import CacheService
from .database import LocalCache

def invalidate_user_cache(user_id: int):
    """Invalide le cache utilisateur (mémoire + Redis)."""
    LocalCache.delete(f"user:{user_id}")
    CacheService.delete(f"user:{user_id}")

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> Utilisateur:
    """
    Dépendance FastAPI pour récupérer l'utilisateur authentifié.
    ZÉRO requête BDD si l'utilisateur est présent dans le cache (optimisé latence réseau).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou token expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        token = request.cookies.get(ACCESS_COOKIE)

    if not token:
        logger.warning("Tentative d'accès sans token d'authentification")
        raise credentials_exception

    try:
        payload = decode_token(token)
        if payload.get("type") not in (None, "access"):
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    cache_key = f"user:{user_id}"
    
    # 🔴 OPTIMISATION LATENCE : Restitution instantanée depuis le cache local (0ms BDD)
    cached_user = LocalCache.get(cache_key) or CacheService.get(cache_key)
    if cached_user:
        user = Utilisateur()
        for k, v in cached_user.items():
            if k == "role_nom" and v:
                from ..models.role import Role
                user.role = Role(nom=v)
            elif hasattr(user, k):
                setattr(user, k, v)
        if getattr(user, 'est_actif', True):
            return user

    user = (
        db.query(Utilisateur)
        .options(joinedload(Utilisateur.role))
        .filter(Utilisateur.id == int(user_id))
        .first()
    )
    if user is None:
        raise credentials_exception

    if not user.est_actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur désactivé",
        )

    user_dict = {
        "id": user.id,
        "email": user.email,
        "nom": user.nom,
        "prenom": user.prenom,
        "post_nom": user.post_nom,
        "role_id": user.role_id,
        "role_nom": user.role.nom if user.role else None,
        "est_actif": user.est_actif
    }
    LocalCache.set(cache_key, user_dict, 600)
    CacheService.set(cache_key, user_dict, ttl=600)
    return user


def get_current_active_user(
    current_user: Utilisateur = Depends(get_current_user)
) -> Utilisateur:
    """
    Dépendance supplémentaire pour vérifier que l'utilisateur est actif.
    Utile si get_current_user ne suffit pas.
    """
    if not current_user.est_actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur inactif"
        )
    return current_user


def check_permission(permission_name: str):
    """
    Factory pour créer une dépendance de vérification de permission.
    Usage: Depends(check_permission("create_bien"))
    """
    def permission_checker(
        current_user: Utilisateur = Depends(get_current_user)
    ) -> Utilisateur:
        if not current_user.has_permission(permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission_name}' requise"
            )
        return current_user
    return permission_checker