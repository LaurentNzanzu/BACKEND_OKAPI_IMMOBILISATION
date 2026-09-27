import logging
import time
import asyncio
from typing import Optional, Tuple, List
from datetime import datetime
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..core.redis_client import redis_client
from ..core.security import decode_token, decode_typed_token, validate_access_session
from ..core.cookies import ACCESS_COOKIE
from jose import JWTError
from ..core.config import settings
from ..services.session_cache_service import SessionCacheService
from ..services.session_service import SessionService
from ..core.database import SessionLocal

logger = logging.getLogger(__name__)


class SessionValidationMiddleware(BaseHTTPMiddleware):
    """
    Validation JWT → blacklist Redis → session SQL → fingerprint.
    Les snapshots Redis ne peuvent pas réactiver une session révoquée en SQL.
    """
    
    # Routes exclues du middleware
    EXCLUDED_PATHS = [
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/api/v1/auth/logout",
        "/api/v1/auth/refresh",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/verify-token",
        "/api/v1/health",
        "/api/v1/health/database",
        "/api/v1/health/jobs",
        "/api/v1/monitoring/redis/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/",
    ]
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.excluded_paths = self.EXCLUDED_PATHS
    
    @staticmethod
    def is_excluded(path: str) -> bool:
        return any(path == item or (item != "/" and path.startswith(item.rstrip("/") + "/"))
                   for item in SessionValidationMiddleware.EXCLUDED_PATHS)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or self.is_excluded(request.url.path):
            return await call_next(request)
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else request.cookies.get(ACCESS_COOKIE)
        # Public routes remain public. Protected routes also enforce their own dependency.
        if not token:
            return await call_next(request)
        try:
            payload = decode_typed_token(token, "access")
            supplied_sid = request.headers.get("X-Session-ID")
            if supplied_sid and supplied_sid != payload["sid"]:
                raise HTTPException(status_code=401, detail="Session incoherente avec le token")
            with SessionLocal() as db:
                session = validate_access_session(db, payload)
                fingerprint = request.headers.get("X-Fingerprint")
                if fingerprint and session.fingerprint and fingerprint != session.fingerprint:
                    SessionService.revoke_all_sessions(db, session.user_id)
                    raise HTTPException(status_code=401, detail="Session compromise detectee")
            request.state.user_id = int(payload["sub"])
            request.state.session_uuid = payload["sid"]
            request.state.jti = payload["jti"]
            request.state.token_exp = payload["exp"]
        except JWTError:
            return JSONResponse(status_code=401, content={"detail": "Token invalide ou expire"})
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except Exception:
            logger.error("Session validation unavailable")
            return JSONResponse(status_code=503, content={"detail": "Validation de session indisponible"})
        asyncio.create_task(self._update_activity_async(int(payload["sub"]), payload["sid"]))
        return await call_next(request)

    async def _update_activity_async(self, user_id: int, session_uuid: str):
        """
        Met à jour l'activité de la session en arrière-plan.
        Non bloquant pour l'utilisateur.
        """
        try:
            db = SessionLocal()
            try:
                # Mettre à jour en BDD
                SessionService.update_session_activity(db, session_uuid)
                logger.debug(f"Activité mise à jour pour session {session_uuid}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Erreur mise à jour activité pour {session_uuid}: {e}")


class TokenValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware pour extraire le JTI du token et le stocker dans request.state.
    Version légère pour les routes qui n'ont pas besoin de validation complète.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.excluded_paths = SessionValidationMiddleware.EXCLUDED_PATHS
    
    async def dispatch(self, request: Request, call_next):
        """
        Extrait le JTI du token JWT et le stocke dans request.state.jti.
        """
        path = request.url.path
        
        # Ignorer les chemins exclus
        if SessionValidationMiddleware.is_excluded(path):
            return await call_next(request)
        
        # Ignorer les requêtes OPTIONS
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Initialiser request.state
        request.state.jti = None
        request.state.user_id = None
        request.state.token_extracted = False
        
        # Récupérer le token depuis le header Authorization
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = decode_typed_token(token, "access")
                jti = payload.get("jti")
                user_id = payload.get("sub")
                if jti and user_id:
                    request.state.jti = jti
                    request.state.user_id = int(user_id)
                    request.state.token_extracted = True
                    logger.debug(f"JTI extrait du token: {jti}")
                else:
                    logger.warning("Token sans JTI ou sub")
            except Exception as e:
                logger.debug(f"Erreur extraction JTI: {e}")
        
        # Continuer le traitement
        response = await call_next(request)
        return response
