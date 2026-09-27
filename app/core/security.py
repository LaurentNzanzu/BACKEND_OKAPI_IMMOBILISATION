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
from ..models.role import Role
from ..models.permission import Permission
from ..core.database import get_db
import logging
import uuid
import hashlib
import hmac
from .redis_client import redis_client
from ..models.session import SessionUtilisateur

logger = logging.getLogger(__name__)

# ============================================================================
# Anciennes clés utilisateur, conservées uniquement pour leur nettoyage.
# get_current_user ne lit ni ne remplit plus ces snapshots d'autorisation.
# ============================================================================
USER_CACHE_VERSION = 2

# Configuration OAuth2 pour extraire le token depuis le header Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

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

def create_access_token(
    user_id: Union[str, int],
    session_uuid: Optional[str] = None,
    jti: Optional[str] = None
) -> str:
    """Crée un token d'accès JWT signé avec JTI et SID (session_uuid)."""
    if jti is None:
        jti = str(uuid.uuid4())

    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "type": "access",
        "jti": jti
    }
    if session_uuid is not None:
        to_encode["sid"] = str(session_uuid)

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: Union[str, int],
    session_uuid: Optional[str] = None,
    jti: Optional[str] = None
) -> str:
    """Crée un refresh token JWT avec JTI et SID (session_uuid)."""
    if jti is None:
        jti = str(uuid.uuid4())

    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti
    }
    if session_uuid is not None:
        to_encode["sid"] = str(session_uuid)

    return jwt.encode(to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str, is_refresh: bool = False) -> dict:
    """Décode et vérifie un token JWT."""
    try:
        secret_key = settings.REFRESH_SECRET_KEY if is_refresh else settings.SECRET_KEY
        return jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM],
                          options={"require_exp": True, "require_sub": True, "require_jti": True})
    except jwt.ExpiredSignatureError:
        logger.warning("Token JWT expiré")
        raise JWTError("Token expiré")
    except jwt.JWTError:
        raise JWTError("Token invalide")


def _reset_password_stamp(user: Utilisateur) -> str:
    # L'empreinte ne divulgue pas le hash ; le domaine distingue cet usage des JWT.
    value = f"password-reset:{user.id}:{user.mot_de_passe}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), value, hashlib.sha256).hexdigest()


def create_password_reset_token(user: Utilisateur) -> str:
    return jwt.encode({"sub": str(user.id), "type": "password_reset",
                       "jti": str(uuid.uuid4()), "pwd": _reset_password_stamp(user),
                       "exp": datetime.utcnow() + timedelta(minutes=5)},
                      settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def validate_reset_payload(payload: dict, user: Utilisateur) -> bool:
    return bool(user and user.est_actif and payload.get("type") == "password_reset"
                and payload.get("sub") == str(user.id)
                and isinstance(payload.get("pwd"), str)
                and hmac.compare_digest(payload["pwd"], _reset_password_stamp(user)))


def require_unrevoked_token(payload: dict):
    """Une blacklist inconnue n'est pas une blacklist vide."""
    try:
        revoked = redis_client.is_blacklisted(payload.get("jti"))
    except Exception:
        revoked = None
    if revoked is None:
        raise HTTPException(status_code=503, detail="Vérification de révocation indisponible")
    if revoked is not False:
        raise HTTPException(status_code=401, detail="Token révoqué")


def decode_typed_token(token: str, token_type: str) -> dict:
    payload = decode_token(token, is_refresh=token_type == "refresh")
    if payload.get("type") != token_type or not payload.get("jti"):
        raise JWTError("Type de token invalide")
    try:
        if int(payload["sub"]) <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise JWTError("Sujet invalide")
    if token_type in ("access", "refresh") and not payload.get("sid"):
        raise JWTError("Session manquante")
    return payload


def validate_access_session(db: Session, payload: dict) -> SessionUtilisateur:
    if payload.get("type") != "access" or not payload.get("sid"):
        raise HTTPException(status_code=401, detail="Token ou session invalide")
    require_unrevoked_token(payload)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token invalide")
    session = (db.query(SessionUtilisateur).filter(
        SessionUtilisateur.session_uuid == payload["sid"],
        SessionUtilisateur.user_id == user_id).populate_existing().first())
    if session is None or session.est_revoquee:
        raise HTTPException(status_code=401, detail="Session révoquée ou introuvable")
    return session


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


def _build_cache_key(user_id: Union[str, int]) -> str:
    """
    ✅ Construit la clé de cache AVEC la version.
    Permet d'invalider les anciennes entrées automatiquement.
    """
    return f"user:{user_id}:v{USER_CACHE_VERSION}"


def _build_cache_key_legacy(user_id: Union[str, int]) -> str:
    """Clé legacy (sans version) — pour supprimer d'éventuels résidus."""
    return f"user:{user_id}"


def invalidate_user_cache(user_id: int) -> bool:
    """
    Invalide le cache utilisateur (mémoire + Redis).
    ✅ Supprime AUSSI les anciennes clés (sans version) par sécurité.
    Retourne False si une suppression échoue, sans interrompre les suivantes.
    Les caches locaux des autres workers expirent par TTL et ne sont plus lus
    par get_current_user. Une panne Redis n'affecte pas l'autorité de la base.
    """
    success = True
    for key in (_build_cache_key(user_id), _build_cache_key_legacy(user_id)):
        for cache in (LocalCache, CacheService):
            try:
                if cache.delete(key) is False:
                    logger.warning("Invalidation incomplète du cache utilisateur : %s", key)
                    success = False
            except Exception:
                logger.warning("Échec d'invalidation du cache utilisateur : %s", key)
                success = False
    return success


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> Utilisateur:
    """
    Retourne l'utilisateur persistant dans la session courante.

    La base est l'autorité pour le statut, le rôle et l'organisation, même si
    un ancien snapshot subsiste dans Redis ou dans un autre worker. Aucun
    objet ORM ni secret n'est reconstruit depuis ou publié dans ce cache.
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
        payload = decode_typed_token(token, "access")
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    session = validate_access_session(db, payload)
    if request is not None:
        request.state.session_uuid = session.session_uuid
        request.state.user_id = session.user_id
        request.state.jti = payload["jti"]
        request.state.token_exp = payload["exp"]

    # Relire aussi une éventuelle instance déjà présente dans l'identity map.
    # Les permissions servent aux gardes existants ; les relations inverses
    # (tous les utilisateurs du rôle, rôles des permissions) restent paresseuses.
    user = (
        db.query(Utilisateur)
        .options(
            joinedload(Utilisateur.role).lazyload(Role.utilisateurs),
            joinedload(Utilisateur.role).selectinload(Role.permissions).lazyload(Permission.roles),
        )
        .populate_existing()
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

    return user


def get_current_active_user(
    current_user: Utilisateur = Depends(get_current_user)
) -> Utilisateur:
    """Dépendance supplémentaire pour vérifier que l'utilisateur est actif."""
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
