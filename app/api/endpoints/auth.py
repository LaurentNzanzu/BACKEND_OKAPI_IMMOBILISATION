from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import logging

import re  # ═══════════════ AJOUT 5.7 — import re pour validation mdp ═══════════════

from ...core.database import get_db
from ...core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    invalidate_user_cache,
    get_token_jti
)
from ...core.cookies import REFRESH_COOKIE, ACCESS_COOKIE
from ...models.session import SessionUtilisateur
from ...services.email_service import EmailService
from ...core.security import (create_password_reset_token, validate_reset_payload,
                              decode_typed_token, require_unrevoked_token)
from jose import JWTError
from urllib.parse import quote
import time
import math
import hmac
import hashlib
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
    PasswordResetResponse,
    VerifyResetTokenRequest,
    ForceChangePasswordRequest,  # ═══════════════ AJOUT 5.7 — schéma force-change ═══════════════
)
from ...models.utilisateur import Utilisateur
from ...models.role import Role
from ...core.config import settings
from ...services.session_service import SessionService
from ...services.session_cache_service import SessionCacheService
from ...core.text_normalization import (
    normalize_email,
    normalize_password,
    detect_ambiguous_chars,
)
# ═══ AJOUT 5.21 — Import AuditService ═══
from ...services.audit_service import AuditService
from ...models.organisation import Organisation
# ═══ FIN AJOUT 5.21 ═══

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

# ════════════════════════════════════════════════════════════════
# ═══ AJOUT 5.23 — Résolution des champs SaaS (multi-tenant)   ═══
# ════════════════════════════════════════════════════════════════
def _resolve_saas_fields(db: Session, user: Utilisateur) -> dict:
    """
    Résout les 5 champs SaaS de UserAuthResponse :
    - organisation_id, is_platform_admin, is_org_admin
    - modules_actifs (depuis organisation.parametres_json)
    - doit_changer_mot_de_passe

    Retourne un dict prêt à passer à UserAuthResponse(**).
    """
    org_id = getattr(user, "organisation_id", None)
    is_platform = bool(getattr(user, "is_platform_admin", False)) or (org_id is None)

    # Résolution des modules actifs
    modules = []
    if org_id:
        org = db.query(Organisation).filter(Organisation.id == org_id).first()
        if org:
            parametres = getattr(org, "parametres_json", None) or {}
            if isinstance(parametres, dict):
                raw = parametres.get("modules_actifs", [])
                if isinstance(raw, list):
                    modules = [str(m) for m in raw if m]

    return {
        "organisation_id": org_id,
        "is_platform_admin": is_platform,
        "is_org_admin": bool(getattr(user, "is_org_admin", False)),
        "modules_actifs": modules,
        "doit_changer_mot_de_passe": bool(getattr(user, "doit_changer_mot_de_passe", False)),
    }
# ═══ FIN AJOUT 5.23 ═══


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

def _build_login_error_message(user: Utilisateur, password_typed: str) -> str:
    """
    Construit un message d'erreur plus utile pour l'utilisateur,
    SANS révéler le mot de passe ni l'existence du compte.

    Guide l'utilisateur vers la résolution du problème.
    """
    base = "Email ou mot de passe incorrect."

    # Cas spécial : admin ONG avec mot de passe temporaire non encore changé
    if getattr(user, "doit_changer_mot_de_passe", False):
        info = detect_ambiguous_chars(password_typed)
        if info["has_ambiguous"]:
            return (
                f"{base} "
                f"⚠️ Votre mot de passe temporaire contient des caractères "
                f"visuellement ambigus. Vérifiez notamment : "
                f"O (lettre) ≠ 0 (chiffre) • l (L minuscule) ≠ 1 (un) ≠ I (i majuscule). "
                f"Conseil : utilisez la fonction « Copier » depuis la page de "
                f"création pour éviter les erreurs de saisie."
            )

    # Message standard pour les autres cas
    return base

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

    ✅ PHASE 5 — Amélioration robustesse :
    - Normalisation de l'email (trim + lowercase + NFC)
    - Normalisation du mot de passe (trim + suppression caractères invisibles)
    - Messages d'erreur pédagogiques pour les caractères ambigus
    - Sécurité inchangée (bcrypt strict)
    """
    email_clean = normalize_email(login_data.email)
    password_clean = normalize_password(login_data.mot_de_passe)

    # Identifiant pseudonymisé : ne pas stocker l'email brut dans Redis.
    identity = hmac.new(
        settings.SECRET_KEY.encode(),
        email_clean.encode(),
        hashlib.sha256
    ).hexdigest()

    login_key = f"login:attempts:{identity}"

    admission = redis_client.admit_login_attempt(
        login_key,
        settings.LOGIN_MAX_ATTEMPTS,
        settings.LOGIN_LOCK_SECONDS
    )

    # Redis indisponible : ne pas autoriser des essais illimités.
    if admission is None:
        raise HTTPException(
            status_code=503,
            detail="Service de connexion temporairement indisponible"
        )

    allowed, retry_after, remaining = admission

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Trop de tentatives. Réessayez après le délai indiqué.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)}
        )

    if not email_clean or not password_clean:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Email ou mot de passe incorrect",
                "remaining_attempts": remaining
            }
        )
    # === 2. RECHERCHE DE L'UTILISATEUR (email insensible à la casse) ===
    user = db.query(Utilisateur).filter(
        func.lower(Utilisateur.email) == email_clean,
        Utilisateur.est_actif == True
    ).with_for_update().first()

    if not user:
        # Message générique : ne pas révéler que l'email n'existe pas
        logger.warning(f"Tentative de connexion : email inconnu ({email_clean})")

        # ═══ AJOUT 5.21 — Log LOGIN_FAILED (email inconnu) ═══
        try:
            AuditService(db).log_login(
                user_id=None,
                email=email_clean,
                success=False,
                request=request,
            )
        except Exception as e:
            logger.warning(f"Échec log audit LOGIN_FAILED (email inconnu) : {e}")
        # ═══ FIN AJOUT 5.21 ═══

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Email ou mot de passe incorrect",
                "remaining_attempts": remaining
            }
        )
    # === 3. VÉRIFICATION DU MOT DE PASSE (STRICT, bcrypt) ===
    if not verify_password(password_clean, user.mot_de_passe):
        # Message enrichi pour guider l'utilisateur
        detail = _build_login_error_message(user, password_clean)

        logger.warning(
            f"Échec de connexion : {email_clean} — "
            f"doit_changer_mdp={getattr(user, 'doit_changer_mot_de_passe', False)}"
        )

        # ═══ AJOUT 5.21 — Log LOGIN_FAILED (mot de passe incorrect) ═══
        try:
            AuditService(db).log_login(
                user_id=None,   # volontairement None : on ne confirme pas l'existence du compte
                email=email_clean,
                success=False,
                request=request,
            )
        except Exception as e:
            logger.warning(f"Échec log audit LOGIN_FAILED (mdp incorrect) : {e}")
        # ═══ FIN AJOUT 5.21 ═══

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": detail,
                "remaining_attempts": remaining
            },
        )

    # === 4. MISE À JOUR DU last_login ===
    user.last_login = datetime.utcnow()

    # === 5. GÉNÉRATION DES TOKENS (inchangé) ===
    session_uuid = str(uuid.uuid4())
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())

    access_token = create_access_token(user.id, session_uuid=session_uuid, jti=access_jti)
    refresh_token = create_refresh_token(user.id, session_uuid=session_uuid, jti=refresh_jti)

    # === 6. INFOS CLIENT ===
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()

    fingerprint = request.headers.get("x-fingerprint")

    # === 7. CRÉATION DE LA SESSION ===
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
                "refresh_jti": refresh_jti,
            },
            session_uuid=session_uuid,
        )
    except Exception as e:
        logger.error(f"Erreur création session : {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la création de la session",
        )

    # === 8. COOKIE REFRESH ===
    set_refresh_token_cookie(response, refresh_token)
    saas_fields = _resolve_saas_fields(db, user)

    # === 9. RÉPONSE ===
    user_response = UserAuthResponse(
        id=user.id,
        email=user.email,
        nom=user.nom,
        post_nom=user.post_nom,
        prenom=user.prenom,
        telephone=user.telephone,
        roles=[user.role.nom] if user.role else [],
        est_actif=user.est_actif,
        last_login=user.last_login,
        **saas_fields,
    )
    # Réinitialiser le compteur après création complète de la session.
    if not redis_client.clear_login_attempts(login_key):
        logger.error("Could not clear login limiter after session creation")

        SessionService.revoke_session(
            db,
            session_uuid,
            user.id
        )

        raise HTTPException(
            status_code=503,
            detail="Service de connexion temporairement indisponible"
        )

    # ═══ AJOUT 5.21 — Log LOGIN_SUCCESS ═══
    try:
        AuditService(db).log_login(
            user_id=user.id,
            email=user.email,
            success=True,
            request=request,
        )
    except Exception as e:
        logger.warning(f"Échec log audit LOGIN_SUCCESS : {e}")
    # ═══ FIN AJOUT 5.21 ═══

    return LoginResponse(
        access_token=access_token,
        session_uuid=session_uuid,
        user=user_response,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    header = request.headers.get("Authorization", "")
    if not token and header.startswith("Bearer "):
        token = header[7:].strip()
    try:
        payload = decode_typed_token(token or "", "refresh")
        require_unrevoked_token(payload)
        # Same lock order as login/reset/password change: user, then session.
        user = (db.query(Utilisateur).filter(Utilisateur.id == int(payload["sub"]))
                .populate_existing().with_for_update().first())
        if not user or not user.est_actif:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable ou desactive")
        session = (db.query(SessionUtilisateur).filter(
            SessionUtilisateur.session_uuid == payload["sid"],
            SessionUtilisateur.user_id == user.id).populate_existing().with_for_update().first())
        if not session or session.est_revoquee or not SessionService.verify_refresh_token(token, session.refresh_token_hash):
            raise HTTPException(status_code=401, detail="Session ou refresh token invalide")
        new_refresh = create_refresh_token(user.id, session_uuid=session.session_uuid)
        new_access = create_access_token(user.id, session_uuid=session.session_uuid)
        old_hash = session.refresh_token_hash
        new_hash = SessionService.hash_refresh_token(new_refresh)
        metadata = dict(session.session_data or {})
        history = list(metadata.get("rotation_history", []))
        history.append({"timestamp": datetime.utcnow().isoformat(), "rotation_number": len(history) + 1})
        metadata.update(rotation_history=history,
                        access_jti=decode_typed_token(new_access, "access")["jti"],
                        refresh_jti=decode_typed_token(new_refresh, "refresh")["jti"])
        # Compare-and-swap also rejects concurrent replays on databases without row locks.
        count = db.query(SessionUtilisateur).filter(
            SessionUtilisateur.id == session.id,
            SessionUtilisateur.refresh_token_hash == old_hash,
            SessionUtilisateur.est_revoquee == False).update({
                SessionUtilisateur.refresh_token_hash: new_hash,
                SessionUtilisateur.date_derniere_activite: datetime.utcnow(),
                SessionUtilisateur.session_data: metadata,
            }, synchronize_session=False)
        if count != 1:
            raise HTTPException(status_code=401, detail="Refresh token deja utilise")
        session_uuid = session.session_uuid
        db.commit()
    except JWTError:
        db.rollback()
        raise HTTPException(status_code=401, detail="Refresh token invalide ou expire")
    except Exception:
        db.rollback()
        raise
    # SQL rotation already prevents replay; optional blacklist writes are post-commit.
    _blacklist_after_commit(payload)
    set_refresh_token_cookie(response, new_refresh)
    return RefreshTokenResponse(access_token=new_access, session_uuid=session_uuid,
                                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


def _blacklist_after_commit(payload: dict):
    ttl = max(0, math.ceil(payload["exp"] - time.time()))
    try:
        if ttl and not redis_client.add_to_blacklist(payload["jti"], ttl):
            logger.warning("SQL revocation/rotation committed; blacklist update failed")
    except Exception:
        logger.warning("SQL revocation/rotation committed; blacklist unavailable")


@router.post("/logout", response_model=LogoutResponse)
async def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    # Bearer identifies the intended session even when a different refresh cookie exists.
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else request.cookies.get(ACCESS_COOKIE)
    token_type = "access"
    if not token:
        token, token_type = request.cookies.get(REFRESH_COOKIE), "refresh"
    if not token:
        clear_refresh_token_cookie(response)
        response.delete_cookie(ACCESS_COOKIE, path="/")
        return LogoutResponse(message="D\u00e9connexion r\u00e9ussie")
    try:
        payload = decode_typed_token(token, token_type)
        uid, sid = int(payload["sub"]), payload["sid"]
        session = (db.query(SessionUtilisateur).filter(
            SessionUtilisateur.session_uuid == sid, SessionUtilisateur.user_id == uid)
            .populate_existing().with_for_update().first())
        if not session:
            raise HTTPException(status_code=401, detail="Session introuvable")
        session.revoke()
        db.commit()
    except JWTError:
        db.rollback()
        raise HTTPException(status_code=401, detail="Token invalide ou expire")
    except Exception:
        db.rollback()
        raise
    SessionService.invalidate_session_cache(uid, sid)
    _blacklist_after_commit(payload)
    clear_refresh_token_cookie(response)
    response.delete_cookie(ACCESS_COOKIE, path="/")
    try:
        AuditService(db).log_logout(user_id=uid, request=request)
    except Exception:
        logger.warning("Logout committed; audit unavailable")
    return LogoutResponse(message="D\u00e9connexion r\u00e9ussie")


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

    saas_fields = _resolve_saas_fields(db, current_user)
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
            last_login=current_user.last_login,
            **saas_fields, 
        ).model_dump(),
        "session_uuid": str(session_uuid) if session_uuid else None
    }


def _password_user(db: Session, current_user: Utilisateur) -> Utilisateur:
    """Relire la ligne courante, sans recopier les attributs du cache.

    Le verrou sérialise les changements concurrents jusqu'au commit/rollback.
    populate_existing rafraîchit aussi une instance déjà dans l'identity map.
    """
    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.id == current_user.id)
        .populate_existing()
        .with_for_update(of=Utilisateur)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Identifiants invalides ou token expiré")
    if not user.est_actif:
        raise HTTPException(status_code=403, detail="Compte utilisateur désactivé")
    return user


def _save_password(db: Session, user: Utilisateur, password: str, keep_session_uuid: str = None):
    """Vérifier les deux champs en base avant de valider leur transaction."""
    user_id = user.id
    try:
        state = inspect(user)
        if not state.persistent or state.session is not db:
            raise RuntimeError("Utilisateur non persistant dans la session courante")
        if keep_session_uuid:
            active = (db.query(SessionUtilisateur).filter(
                SessionUtilisateur.session_uuid == keep_session_uuid,
                SessionUtilisateur.user_id == user_id).populate_existing().with_for_update().first())
            if not active or active.est_revoquee:
                raise HTTPException(status_code=401, detail="Session révoquée")
        password_hash = get_password_hash(password)
        user.mot_de_passe = password_hash
        user.doit_changer_mot_de_passe = False
        db.flush()
        db.refresh(user, attribute_names=["mot_de_passe", "doit_changer_mot_de_passe"])
        if user.mot_de_passe != password_hash or user.doit_changer_mot_de_passe is not False:
            raise RuntimeError("Changement de mot de passe non persisté")
        SessionService.revoke_sessions_in_transaction(db, user_id, keep_session_uuid)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # La transaction est déjà validée : une panne de cache ne l'annule pas.
    try:
        if invalidate_user_cache(user_id) is False:
            logger.warning("Mot de passe enregistré ; invalidation du cache incomplète pour #%s", user_id)
    except Exception:
        logger.warning("Mot de passe enregistré ; échec d'invalidation du cache pour #%s", user_id)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    http_request: Request,
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change le mot de passe de l'utilisateur.
    """
    current_user = _password_user(db, current_user)
    # Vérification de l'ancien mot de passe depuis la base, jamais depuis le cache.
    if not verify_password(request.ancien_mot_de_passe, current_user.mot_de_passe):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ancien mot de passe incorrect"
        )
    
    # Mise à jour du mot de passe
    _save_password(db, current_user, request.nouveau_mot_de_passe,
                   getattr(http_request.state, "session_uuid", None))
    
    return {"message": "Mot de passe modifié avec succès"}

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(Utilisateur).filter(
        func.lower(Utilisateur.email) == normalize_email(request.email),
        Utilisateur.est_actif == True).first()
    if user:
        if EmailService.is_configured():
            token = create_password_reset_token(user)
            link = settings.FRONTEND_URL.rstrip("/") + "/reset-password?token=" + quote(token, safe="")
            try:
                if not EmailService.send_password_reset_email(user.email, link):
                    logger.warning("Password reset delivery failed")
            except Exception:
                logger.warning("Password reset delivery unavailable")
        else:
            logger.warning("Password reset requires configured SMTP; no token delivered")
    return {"message": "Si un compte existe, un email de r\u00e9initialisation a \u00e9t\u00e9 envoy\u00e9"}


@router.post("/verify-token")
async def verify_reset_token(request: VerifyResetTokenRequest, response: Response,
                             db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    try:
        payload = decode_typed_token(request.token, "password_reset")
        require_unrevoked_token(payload)
        user = db.query(Utilisateur).filter(Utilisateur.id == int(payload["sub"])).first()
        if validate_reset_payload(payload, user):
            return {"valid": True, "user_id": user.id}
    except JWTError:
        pass
    return {"valid": False}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_typed_token(request.token, "password_reset")
        require_unrevoked_token(payload)
        user = (db.query(Utilisateur).filter(Utilisateur.id == int(payload["sub"]))
                .populate_existing().with_for_update().first())
        if not validate_reset_payload(payload, user):
            raise HTTPException(status_code=400, detail="Token invalide, expire ou deja utilise")
        # Changing the hash consumes every reset token issued against the previous hash.
        _save_password(db, user, request.nouveau_mot_de_passe)
    except JWTError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Token invalide ou expire")
    except Exception:
        db.rollback()
        raise
    return {"message": "Mot de passe r\u00e9initialis\u00e9 avec succ\u00e8s"}


@router.post("/token")
async def login_oauth2_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
):
    """
    Endpoint OAuth2 dédié à Swagger UI.
    
    Accepte le format `application/x-www-form-urlencoded` avec :
    - `username` : l'email de l'utilisateur
    - `password` : le mot de passe
    
    Réutilise la logique du endpoint `/login` (aucune duplication de code).
    """
    # 1. Convertir le format OAuth2 (username/password) vers LoginRequest (email/mot_de_passe)
    login_data = LoginRequest(
        email=form_data.username,
        mot_de_passe=form_data.password,
    )
    
    # 2. Appeler la même logique que /login (aucune modification)
    result = await login(
        login_data=login_data,
        request=request,
        response=response,
        db=db,
    )
    
    # 3. Retourner avec `token_type` requis par la spécification OAuth2
    #    (Swagger l'exige, votre frontend ne l'utilise pas)
    return {
        "access_token": result.access_token,
        "token_type": "bearer",              # ⬅️ Exigé par Swagger
        "session_uuid": result.session_uuid,
        "expires_in": result.expires_in,
        "user": result.user,
    }


# ═══════════════ AJOUT 5.7 — DÉBUT ═══════════════

@router.post("/force-change-password")
async def force_change_password(
    request: ForceChangePasswordRequest,
    http_request: Request,
    current_user: Utilisateur = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change le mot de passe lors de la PREMIÈRE CONNEXION de l'admin ONG.

    Contexte :
    - L'admin ONG est créé automatiquement avec un mot de passe temporaire
    - `doit_changer_mot_de_passe = True` jusqu'à ce qu'il change son mot de passe
    - Cet endpoint ne nécessite PAS l'ancien mot de passe (déjà validé au login)

    Règles de validation du nouveau mot de passe :
    - 8 caractères minimum
    - Au moins 1 majuscule
    - Au moins 1 minuscule
    - Au moins 1 chiffre
    """
    current_user = _password_user(db, current_user)
    # 1. Vérifier en base que le changement est bien requis
    if not getattr(current_user, "doit_changer_mot_de_passe", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun changement de mot de passe forcé n'est requis pour ce compte.",
        )

    # 2. Valider le nouveau mot de passe
    nouveau = request.nouveau_mot_de_passe or ""
    erreurs = []
    if len(nouveau) < 8:
        erreurs.append("au moins 8 caractères")
    if not re.search(r"[A-Z]", nouveau):
        erreurs.append("au moins une majuscule")
    if not re.search(r"[a-z]", nouveau):
        erreurs.append("au moins une minuscule")
    if not re.search(r"\d", nouveau):
        erreurs.append("au moins un chiffre")

    if erreurs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe invalide : " + ", ".join(erreurs) + ".",
        )

    # 3. Mettre à jour le mot de passe + retirer le flag
    _save_password(db, current_user, nouveau,
                   getattr(http_request.state, "session_uuid", None))

    logger.info(
        f"Mot de passe forcé changé avec succès pour l'utilisateur "
        f"#{current_user.id} ({current_user.email})"
    )

    return {
        "success": True,
        "message": "Mot de passe changé avec succès. Vous pouvez maintenant utiliser l'application.",
        "doit_changer_mot_de_passe": False,
    }
