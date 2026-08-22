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
import uuid  # ⬅️ Ajouté pour générer des JTI uniques

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

def create_access_token(user_id: Union[str, int], jti: Optional[str] = None) -> str:
    """
    Crée un token d'accès JWT signé avec JTI.
    Durée de vie : 15 minutes (configurable via settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    """
    if jti is None:
        jti = str(uuid.uuid4())  # Génère un JTI unique
    
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "type": "access",
        "jti": jti
    }
    
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: Union[str, int], jti: Optional[str] = None) -> str:
    """
    Crée un refresh token JWT avec JTI.
    Durée de vie : 7 jours (configurable via settings.REFRESH_TOKEN_EXPIRE_DAYS)
    """
    if jti is None:
        jti = str(uuid.uuid4())  # Génère un JTI unique
    
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti
    }
    
    # Utilise une clé séparée pour les refresh tokens
    return jwt.encode(to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str, is_refresh: bool = False) -> dict:
    """
    Décode et vérifie un token JWT.
    is_refresh: Si True, utilise la clé de refresh, sinon la clé d'access.
    """
    try:
        secret_key = settings.REFRESH_SECRET_KEY if is_refresh else settings.SECRET_KEY
        return jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])
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


def get_token_jti(token: str, is_refresh: bool = False) -> Optional[str]:
    """Extrait le JTI d'un token."""
    try:
        payload = decode_token(token, is_refresh)
        return payload.get("jti")
    except JWTError:
        return None


# === Dépendance d'authentification ===

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

    # Récupère l'Access Token depuis le header Authorization ou depuis le cookie
    if not token:
        token = request.cookies.get(ACCESS_COOKIE)

    if not token:
        logger.warning("Tentative d'accès sans token d'authentification")
        raise credentials_exception

    try:
        payload = decode_token(token, is_refresh=False)  # Token d'access
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    cache_key = f"user:{user_id}"
    
    # OPTIMISATION LATENCE : Restitution instantanée depuis le cache local
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