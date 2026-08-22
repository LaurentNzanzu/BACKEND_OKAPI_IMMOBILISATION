from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import logging

from ...core.database import get_db
from ...core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_token_jti
)
from ...core.cookies import REFRESH_COOKIE
from ...core.redis_client import redis_client
from ...schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenResponse,
    LogoutResponse,
    UserAuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PasswordResetResponse
)
from ...models.utilisateur import Utilisateur
from ...models.role import Role
from ...core.config import settings
from ...services.session_service import SessionService
from ...services.session_cache_service import SessionCacheService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# === COOKIE CONFIGURATION ===
def set_refresh_token_cookie(response: Response, token: str):
    """Définit le cookie refresh token avec les attributs de sécurité."""
    secure = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_refresh_token_cookie(response: Response):
    """Supprime le cookie refresh token."""
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path="/",
        secure=settings.ENVIRONMENT == "production",
        httponly=True,
        samesite="strict",
    )


# === ROUTES ===

@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authentifie un utilisateur et génère un Access Token + Refresh Token.
    Crée une session en base de données pour la traçabilité.
    """
    # 1. Recherche de l'utilisateur
    user = db.query(Utilisateur).filter(
        Utilisateur.email == login_data.email,
        Utilisateur.est_actif == True
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    
    # 2. Vérification du mot de passe
    if not verify_password(login_data.mot_de_passe, user.mot_de_passe):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )
    
    # 3. Mise à jour de last_login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # 4. Génération des tokens
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    
    access_token = create_access_token(user.id, jti=access_jti)
    refresh_token = create_refresh_token(user.id, jti=refresh_jti)
    
    # 5. Récupération des informations client
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    
    # Récupérer l'IP via X-Forwarded-For si derrière un proxy
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    fingerprint = request.headers.get("x-fingerprint")
    
    # 6. CRÉATION DE LA SESSION EN BDD
    try:
        session = SessionService.create_session(
            db=db,
            user_id=user.id,
            refresh_token=refresh_token,
            user_agent=user_agent,
            ip_address=ip_address,
            fingerprint=fingerprint,
            session_data={
                "login_method": "password",
                "access_jti": access_jti,
                "refresh_jti": refresh_jti
            }
        )
        session_uuid = str(session.session_uuid)
    except Exception as e:
        logger.error(f"Erreur lors de la création de la session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la création de la session"
        )
    
    # 7. Définition du cookie refresh token
    set_refresh_token_cookie(response, refresh_token)
    
    # 8. Construction de la réponse
    user_response = UserAuthResponse(
        id=user.id,
        email=user.email,
        nom=user.nom,
        post_nom=user.post_nom,
        prenom=user.prenom,
        telephone=user.telephone,
        roles=[user.role.nom] if user.role else [],
        est_actif=user.est_actif,
        last_login=user.last_login
    )
    
    return LoginResponse(
        access_token=access_token,
        session_uuid=session_uuid,
        user=user_response,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Rafraîchit l'Access Token en utilisant le Refresh Token.
    Effectue une rotation du Refresh Token avec validation de session.
    🔴 NOUVEAU : Blacklist l'ancien Refresh Token.
    """
    # 1. Récupération du refresh token depuis le cookie
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token manquant"
        )
    
    try:
        # 2. Décodage du refresh token
        payload = decode_token(refresh_token, is_refresh=True)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide"
            )
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide"
            )
        
        # 🔴 NOUVEAU : Récupérer le JTI de l'ancien refresh token
        old_refresh_jti = payload.get("jti")
        
        # 3. Vérification que l'utilisateur existe
        user = db.query(Utilisateur).filter(
            Utilisateur.id == int(user_id),
            Utilisateur.est_actif == True
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utilisateur introuvable ou désactivé"
            )
        
        # 4. Récupération du session_uuid depuis le token
        session_uuid = payload.get("sid")
        
        if not session_uuid:
            # Fallback: essayer de récupérer par le hash du refresh token
            refresh_hash = SessionService.hash_refresh_token(refresh_token)
            session = SessionService.get_session_by_refresh_token_hash(db, refresh_hash)
            if session:
                session_uuid = str(session.session_uuid)
        
        # 5. VALIDATION DE LA SESSION EN BDD
        if not session_uuid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session invalide"
            )
        
        # Vérifier que la session existe et est active
        is_valid = SessionService.validate_session(
            db, 
            session_uuid, 
            refresh_token=refresh_token,
            user_id=int(user_id)
        )
        
        if not is_valid:
            logger.warning(f"Session invalide ou révoquée: {session_uuid}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session révoquée ou expirée"
            )
        
        # 6. 🔴 NOUVEAU : BLACKLISTER L'ANCIEN REFRESH TOKEN
        if old_refresh_jti:
            # TTL = 7 jours (durée de vie du refresh token)
            refresh_ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            blacklist_success = redis_client.add_to_blacklist(old_refresh_jti, refresh_ttl)
            if blacklist_success:
                logger.info(f"Ancien Refresh Token JTI {old_refresh_jti} blacklisté")
            else:
                logger.warning(f"Échec blacklist de l'ancien Refresh Token {old_refresh_jti}")
        
        # 7. ROTATION : Génération d'un nouveau refresh token
        new_refresh_jti = str(uuid.uuid4())
        new_refresh_token = create_refresh_token(user_id, jti=new_refresh_jti)
        
        # 8. ROTATION : Mise à jour de la session en BDD
        rotation_success = SessionService.rotate_session(
            db, 
            session_uuid, 
            new_refresh_token,
            user_id=int(user_id)
        )
        
        if not rotation_success:
            logger.error(f"Échec de rotation pour la session {session_uuid}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la rotation de session"
            )
        
        # 9. Génération d'un nouveau access token
        new_access_jti = str(uuid.uuid4())
        new_access_token = create_access_token(user_id, jti=new_access_jti)
        
        # 10. Mise à jour du cookie avec le nouveau refresh token
        set_refresh_token_cookie(response, new_refresh_token)
        
        # 11. Mise à jour de l'activité de la session
        SessionService.update_session_activity(db, session_uuid)
        
        return RefreshTokenResponse(
            access_token=new_access_token,
            session_uuid=str(session_uuid),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expiré"
        )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Déconnecte l'utilisateur en supprimant le cookie refresh token
    et en révoquant la session en base de données.
    🔴 NOUVEAU : Ajoute l'Access Token à la blacklist pour une révocation instantanée.
    """
    # 1. Récupérer le session_uuid depuis le refresh token ou le payload
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    session_uuid = None
    user_id = None
    access_jti = None
    
    # 2. Récupérer le JTI de l'Access Token depuis request.state
    if hasattr(request.state, 'jti') and request.state.jti:
        access_jti = request.state.jti
        logger.debug(f"JTI de l'Access Token récupéré: {access_jti}")
    else:
        # Essayer de récupérer depuis le header Authorization
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                payload = decode_token(token, is_refresh=False)
                access_jti = payload.get("jti")
                user_id = payload.get("sub")
                logger.debug(f"JTI extrait du token: {access_jti}")
            except Exception as e:
                logger.warning(f"Impossible d'extraire le JTI: {e}")
    
    if refresh_token:
        try:
            # Extraire le session_uuid du token (si stocké)
            payload = decode_token(refresh_token, is_refresh=True)
            session_uuid = payload.get("sid")
            if not user_id:
                user_id = payload.get("sub")
        except Exception as e:
            logger.warning(f"Impossible de décoder le refresh token: {e}")
    
    # 3. Si session_uuid non trouvé, essayer de récupérer par hash
    if not session_uuid and refresh_token:
        refresh_hash = SessionService.hash_refresh_token(refresh_token)
        session = SessionService.get_session_by_refresh_token_hash(db, refresh_hash)
        if session:
            session_uuid = session.session_uuid
            if not user_id:
                user_id = session.user_id
    
    # 4. 🔴 NOUVEAU : BLACKLISTER L'ACCESS TOKEN
    if access_jti:
        # Calculer le TTL restant (durée de vie de l'Access Token)
        # Par défaut, on utilise la durée de vie configurée
        remaining_ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 15 min
        
        # Si on a l'expiration réelle, on peut calculer le TTL exact
        if hasattr(request.state, 'token_exp') and request.state.token_exp:
            now = datetime.utcnow().timestamp()
            remaining_ttl = max(0, int(request.state.token_exp - now))
        
        if remaining_ttl > 0:
            blacklist_success = redis_client.add_to_blacklist(access_jti, remaining_ttl)
            if blacklist_success:
                logger.info(f"Access Token JTI {access_jti} blacklisté (TTL: {remaining_ttl}s)")
            else:
                logger.warning(f"Échec blacklist de l'Access Token {access_jti}")
        else:
            logger.debug(f"Access Token JTI {access_jti} déjà expiré, pas de blacklist")
    
    # 5. RÉVOCATION DE LA SESSION EN BDD ET REDIS
    if session_uuid and user_id:
        # Révocation en BDD
        revoked = SessionService.revoke_session(
            db, 
            session_uuid, 
            user_id=int(user_id) if user_id else None,
            reason="Logout explicite"
        )
        if revoked:
            logger.info(f"Session {session_uuid} révoquée (logout)")
        
        # Révocation en Redis
        try:
            SessionCacheService.revoke_session_cache(int(user_id), session_uuid)
            logger.debug(f"Session {session_uuid} révoquée en Redis")
        except Exception as e:
            logger.warning(f"Erreur révocation Redis pour {session_uuid}: {e}")
    
    # 6. Nettoyer le cookie refresh token
    clear_refresh_token_cookie(response)
    
    return LogoutResponse(message="Déconnexion réussie")


@router.get("/me")
async def get_me(
    request: Request,
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Récupère les informations de l'utilisateur authentifié
    ainsi que l'UUID de sa session active.
    """
    # Récupérer le session_uuid actuel
    session_uuid = None
    
    # Essayer de récupérer depuis le token d'access (si stocké)
    access_token = request.headers.get("Authorization")
    if access_token and access_token.startswith("Bearer "):
        try:
            token = access_token.split(" ")[1]
            payload = decode_token(token, is_refresh=False)
            session_uuid = payload.get("sid")
        except Exception as e:
            logger.warning(f"Impossible de décoder l'access token: {e}")
    
    # Si non trouvé, récupérer la session active la plus récente
    if not session_uuid:
        active_sessions = SessionService.get_user_active_sessions(db, current_user.id, limit=1)
        if active_sessions:
            session_uuid = active_sessions[0].session_uuid
    
    return {
        **UserAuthResponse(
            id=current_user.id,
            email=current_user.email,
            nom=current_user.nom,
            post_nom=current_user.post_nom,
            prenom=current_user.prenom,
            telephone=current_user.telephone,
            roles=[current_user.role.nom] if current_user.role else [],
            est_actif=current_user.est_actif,
            last_login=current_user.last_login
        ).model_dump(),
        "session_uuid": str(session_uuid) if session_uuid else None
    }


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change le mot de passe de l'utilisateur.
    """
    # Vérification de l'ancien mot de passe
    if not verify_password(request.ancien_mot_de_passe, current_user.mot_de_passe):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ancien mot de passe incorrect"
        )
    
    # Mise à jour du mot de passe
    current_user.mot_de_passe = get_password_hash(request.nouveau_mot_de_passe)
    db.commit()
    
    return {"message": "Mot de passe modifié avec succès"}

@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Génère un token de réinitialisation et le renvoie pour l'affichage direct.
    """
    user = db.query(Utilisateur).filter(
        Utilisateur.email == request.email
    ).first()
    
    if not user:
        return {"message": "Si un compte existe, un email de réinitialisation a été envoyé"}
    
    # Génération du token
    reset_token = create_access_token(
        user.id,
        jti=f"reset_{uuid.uuid4()}"
    )
    
    logger.info(f"Reset token pour {user.email}: {reset_token}")
    
    # 👈 ON RENVOIE LE TOKEN DANS LA RÉPONSE
    return {
        "message": "Si un compte existe, un email de réinitialisation a été envoyé",
        "reset_token": reset_token
    }

@router.get("/verify-token/{token}")
async def verify_reset_token(
    token: str
):
    """
    Vérifie si un token de réinitialisation est valide.
    """
    try:
        payload = decode_token(token, is_refresh=False)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token invalide"
            )
        return {"valid": True, "user_id": payload.get("sub")}
    except Exception:
        return {"valid": False}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Réinitialise le mot de passe avec un token valide.
    """
    try:
        # Vérification du token
        payload = decode_token(request.token, is_refresh=False)
        
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token invalide"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token invalide"
            )
        
        # Récupération de l'utilisateur
        user = db.query(Utilisateur).filter(
            Utilisateur.id == int(user_id)
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur introuvable"
            )
        
        # Mise à jour du mot de passe
        user.mot_de_passe = get_password_hash(request.nouveau_mot_de_passe)
        db.commit()
        
        return {"message": "Mot de passe réinitialisé avec succès"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la réinitialisation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token invalide ou expiré"
        )