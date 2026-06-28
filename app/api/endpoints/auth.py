from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Any, Optional
import logging

from ...core.database import get_db
from ...core.cookies import set_auth_cookies, clear_auth_cookies, REFRESH_COOKIE
from ...schemas.auth import (
    LoginCredentials,
    LoginResponse,
    LogoutResponse,
    RefreshTokenRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserAuthResponse,
    PasswordResetResponse,
)
from ...services.auth_service import AuthService
from ...services.audit_service import AuditService
from ...services.password_reset_service import PasswordResetService
from ...services.email_service import EmailService
from ...api.dependencies import get_current_user
from ...models.utilisateur import Utilisateur
from ...core.security import get_password_hash, decode_token, create_access_token, invalidate_user_cache
from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(
    request: Request,
    credentials: LoginCredentials,
    db: Session = Depends(get_db),
) -> Any:
    audit_service = AuditService(db)
    user = AuthService.authenticate_user(db, credentials.email, credentials.mot_de_passe)

    if not user:
        audit_service.log_action(
            user_id=None,
            table_name="utilisateurs",
            record_id=None,
            action="LOGIN_FAILED",
            anciennes_valeurs=None,
            nouvelles_valeurs={"email_tente": credentials.email, "ip": request.client.host if request.client else None},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = AuthService.create_tokens(user.id)
    AuthService.update_last_login(db, user, audit_service)
    roles = AuthService.get_user_roles(db, user)

    user_response = UserAuthResponse(
        id=user.id,
        email=user.email,
        nom=user.nom,
        post_nom=user.post_nom,
        prenom=user.prenom,
        telephone=user.telephone,
        roles=roles,
        est_actif=user.est_actif,
        last_login=user.last_login,
    )

    logger.info("Connexion réussie : %s (ID: %s)", user.email, user.id)

    payload = LoginResponse(message="Connexion réussie", user=user_response).model_dump(mode="json")
    response = JSONResponse(content=payload)
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    return response


@router.post("/refresh", response_model=Token)
def refresh_token(
    request: Request,
    body: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
) -> Any:
    refresh_value = request.cookies.get(REFRESH_COOKIE)
    if not refresh_value and body and body.refresh_token:
        refresh_value = body.refresh_token

    if not refresh_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token manquant")

    try:
        payload = decode_token(refresh_value)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

        user = db.query(Utilisateur).filter(Utilisateur.id == int(user_id)).first()
        if not user or not user.est_actif:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur invalide ou désactivé")

        new_access_token = create_access_token(user.id)
        token_response = Token(
            access_token=new_access_token,
            refresh_token=refresh_value,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        response = JSONResponse(content=token_response.model_dump(mode="json"))
        set_auth_cookies(response, new_access_token, refresh_value)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erreur refresh token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expiré",
        )


@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
def logout(
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    audit_service = AuditService(db)
    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=current_user.id,
        action="LOGOUT",
        anciennes_valeurs=None,
        nouvelles_valeurs=None,
    )
    logger.info("Déconnexion : %s", current_user.email)
    invalidate_user_cache(current_user.id)
    response = JSONResponse(content={"message": "Déconnexion réussie"})
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserAuthResponse)
def get_current_user_info(
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    roles = AuthService.get_user_roles(db, current_user)
    return UserAuthResponse(
        id=current_user.id,
        email=current_user.email,
        nom=current_user.nom,
        post_nom=current_user.post_nom,
        prenom=current_user.prenom,
        telephone=current_user.telephone,
        roles=roles,
        est_actif=current_user.est_actif,
        last_login=current_user.last_login,
    )


@router.put("/me/password", response_model=dict)
def change_password(
    request: ChangePasswordRequest,
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    from ...core.security import verify_password

    if not verify_password(request.ancien_mot_de_passe, current_user.mot_de_passe):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="L'ancien mot de passe est incorrect")

    current_user.mot_de_passe = get_password_hash(request.nouveau_mot_de_passe)
    db.commit()

    audit_service = AuditService(db)
    audit_service.log_action(
        user_id=current_user.id,
        table_name="utilisateurs",
        record_id=current_user.id,
        action="PASSWORD_CHANGED",
        anciennes_valeurs=None,
        nouvelles_valeurs={"mot_de_passe": "****"},
    )

    logger.info("Mot de passe changé pour l'utilisateur %s", current_user.email)
    return {"message": "Mot de passe mis à jour avec succès"}


@router.post("/forgot-password", response_model=PasswordResetResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    user = db.query(Utilisateur).filter(Utilisateur.email == request.email).first()
    generic_message = PasswordResetResponse(message="Si un compte correspond, un lien a été envoyé.")

    if not user or not user.est_actif:
        return generic_message

    reset_service = PasswordResetService(db)
    raw_token = reset_service.create_reset_token(user.id)
    reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={raw_token}"

    EmailService.send_password_reset_email(user.email, reset_link)

    audit_service = AuditService(db)
    audit_service.log_action(
        user_id=user.id,
        table_name="utilisateurs",
        record_id=user.id,
        action="PASSWORD_RESET_REQUESTED",
        anciennes_valeurs=None,
        nouvelles_valeurs={"email": user.email},
    )
    logger.info("Demande de réinitialisation enregistrée pour: %s", user.email)
    return generic_message


@router.post("/reset-password", response_model=PasswordResetResponse)
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    reset_service = PasswordResetService(db)
    user = reset_service.consume_token(request.token)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token invalide ou expiré")

    user.mot_de_passe = get_password_hash(request.nouveau_mot_de_passe)
    db.commit()

    audit_service = AuditService(db)
    audit_service.log_action(
        user_id=user.id,
        table_name="utilisateurs",
        record_id=user.id,
        action="PASSWORD_RESET_COMPLETED",
        anciennes_valeurs=None,
        nouvelles_valeurs=None,
    )
    logger.info("Mot de passe réinitialisé pour: %s", user.email)
    return PasswordResetResponse(message="Mot de passe réinitialisé avec succès")


@router.get("/verify-token/{token}")
async def verify_token(token: str, db: Session = Depends(get_db)):
    reset_service = PasswordResetService(db)
    return {"valid": reset_service.verify_token(token)}
