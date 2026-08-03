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
from ..core.security import decode_token
from ..core.config import settings
from ..services.session_cache_service import SessionCacheService
from ..services.session_service import SessionService
from ..core.database import SessionLocal

logger = logging.getLogger(__name__)


class SessionValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware de validation des sessions avec vérifications en cascade.
    Ordre des vérifications : JWT → Blacklist → Session → Fingerprint
    Performance cible : < 2ms par requête
    """
    
    # Routes exclues du middleware
    EXCLUDED_PATHS = [
        "/api/v1/auth/login",
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
    
    async def dispatch(self, request: Request, call_next):
        """
        Exécute la validation de session pour chaque requête.
        """
        start_time = time.time()
        path = request.url.path
        
        # 1. Vérifier si la route est exclue
        if any(path.startswith(exclude) for exclude in self.excluded_paths):
            return await call_next(request)
        
        # 2. Ignorer les requêtes OPTIONS (CORS)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # 3. Initialiser request.state
        request.state.user_id = None
        request.state.session_uuid = None
        request.state.jti = None
        request.state.token_exp = None
        request.state.fingerprint = None
        
        try:
            # ============================================================
            # ÉTAPE 1 : VÉRIFICATION DU JWT
            # ============================================================
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.warning(f"Token manquant pour {path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token d'authentification manquant"}
                )
            
            token = auth_header.split(" ")[1]
            
            try:
                payload = decode_token(token, is_refresh=False)
            except Exception as e:
                logger.warning(f"Token invalide pour {path}: {e}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token invalide ou expiré"}
                )
            
            # Vérifier le type du token
            if payload.get("type") != "access":
                logger.warning(f"Token de type incorrect pour {path}: {payload.get('type')}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token invalide"}
                )
            
            # Extraire les données
            user_id = payload.get("sub")
            jti = payload.get("jti")
            exp = payload.get("exp")
            
            if not user_id or not jti:
                logger.warning(f"Token sans sub ou jti pour {path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token invalide (données manquantes)"}
                )
            
            # Stocker dans request.state
            request.state.user_id = int(user_id)
            request.state.jti = jti
            request.state.token_exp = exp
            
            # ============================================================
            # ÉTAPE 2 : VÉRIFICATION DE LA BLACKLIST
            # ============================================================
            is_blacklisted = redis_client.is_blacklisted(jti)
            if is_blacklisted:
                logger.warning(f"Token JTI {jti} blacklisté pour {path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token révoqué (blacklist)"}
                )
            
            # ============================================================
            # ÉTAPE 3 : RÉCUPÉRATION DU SESSION_UUID
            # ============================================================
            session_uuid = request.headers.get("X-Session-ID")
            fingerprint = request.headers.get("X-Fingerprint")
            request.state.fingerprint = fingerprint
            
            if not session_uuid:
                # Essayer de récupérer depuis le token (si stocké)
                session_uuid = payload.get("sid")
            
            if not session_uuid:
                logger.warning(f"Session ID manquant pour {path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Session ID manquant"}
                )
            
            request.state.session_uuid = session_uuid
            
            # ============================================================
            # ÉTAPE 4 : VÉRIFICATION DE LA SESSION (Redis → BDD)
            # ============================================================
            # Créer une session BDD pour la validation
            db = SessionLocal()
            try:
                # Valider la session via le cache
                is_valid, message = SessionCacheService.validate_session(
                    db=db,
                    user_id=int(user_id),
                    session_uuid=session_uuid,
                    fingerprint=fingerprint
                )
                
                if not is_valid:
                    logger.warning(f"Session invalide pour {path}: {message}")
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": message}
                    )
                
                # ============================================================
                # ÉTAPE 5 : VÉRIFICATION DU FINGERPRINT (déjà faite dans validate_session)
                # ============================================================
                # La vérification du fingerprint est déjà faite dans validate_session
                # Si mismatch, elle retourne False avec message "Session compromise détectée"
                
                # ============================================================
                # ÉTAPE 6 : MISE À JOUR DE L'ACTIVITÉ (ASYNCHRONE)
                # ============================================================
                # Planifier la mise à jour en arrière-plan
                asyncio.create_task(
                    self._update_activity_async(int(user_id), session_uuid)
                )
                
                # ============================================================
                # ÉTAPE 7 : CONTINUER LE TRAITEMENT
                # ============================================================
                elapsed = (time.time() - start_time) * 1000
                logger.debug(
                    f"Session validée: {session_uuid} pour user {user_id} "
                    f"(Temps: {elapsed:.2f}ms)"
                )
                
                # Ajouter des informations à request.state pour les routes
                request.state.is_validated = True
                request.state.validation_time_ms = elapsed
                
                # Continuer vers la route
                response = await call_next(request)
                
                # Ajouter des headers de performance (optionnel)
                if settings.DEBUG:
                    response.headers["X-Validation-Time"] = f"{elapsed:.2f}ms"
                    response.headers["X-Session-UUID"] = session_uuid[:8]
                
                return response
                
            finally:
                db.close()
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue dans le middleware: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Erreur interne du serveur"}
            )
    
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
        if any(path.startswith(exclude) for exclude in self.excluded_paths):
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
                payload = decode_token(token, is_refresh=False)
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