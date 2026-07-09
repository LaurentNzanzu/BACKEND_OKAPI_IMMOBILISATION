# coding: utf-8
import re
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import os
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.database import engine, Base, get_db, SessionLocal
from app.core.config import settings
from app.core.middleware_perf import PerformanceLoggingMiddleware

import app.models

from app.api.endpoints import (
    auth,
    utilisateurs,
    roles,
    biens,
    vehicules,
    machines,
    ordinateurs,
    composants,
    maintenances,
    validations,
    pannes,
    pieces,
    besoins,
    qr_code,
    amortissements,
    ecritures_comptables,
    regles_amortissement,
    mouvements,
    notifications,
    dashboard,
    audit,
    rapports,
    ia_decision,
    etats,
    fournitures,
    cessions,
    plan_comptable,
    fournisseurs,
    localisations,
    budgets,
    caisse,
    mouvements_caisse,
    pieces_justificatives,
    etats_financiers,
)

# Import des tâches CRON
from .tasks import (
    init_scores_scheduler,
    init_alertes_scheduler,
    init_projections_scheduler
)

logger = logging.getLogger(__name__)

# Variable globale pour le scheduler
scheduler = None

API_V1_PREFIX = "/api/v1"
_API_COLLECTION_PATH = re.compile(r"^/api/v1/[^/]+$")


class ApiCollectionSlashMiddleware(BaseHTTPMiddleware):
    """Accepte les URLs de collection sans slash final (redirect_slashes désactivé)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _API_COLLECTION_PATH.match(path):
            request.scope["path"] = f"{path}/"
            request.scope["raw_path"] = f"{path}/".encode("latin-1")
        return await call_next(request)


# ============================================================
# GESTIONNAIRES D'EXCEPTIONS GLOBAUX
# ============================================================

async def global_exception_handler(request: Request, exc: Exception):
    """
    Capture TOUTES les exceptions non gérées.
    En production, masque les détails sensibles.
    """
    logger.error(
        f"Exception non gérée sur {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={
            "client_host": request.client.host if request.client else None,
            "path": request.url.path,
            "method": request.method,
        }
    )
    
    # En production, ne JAMAIS exposer le détail de l'erreur
    if settings.ENVIRONMENT == "production":
        message = "Une erreur interne est survenue. L'incident a été signalé."
        detail = None
    else:
        message = str(exc)
        detail = {
            "type": exc.__class__.__name__,
            "path": request.url.path
        }
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "code": "INTERNAL_ERROR",
            "message": message,
            "detail": detail
        }
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """
    Gère les erreurs de base de données.
    503 Service Unavailable car souvent temporaire (timeout, verrou).
    """
    logger.error(
        f"Erreur base de données sur {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "code": "DATABASE_ERROR",
            "message": "Erreur de base de données. Veuillez réessayer dans quelques instants.",
            "detail": None if settings.ENVIRONMENT == "production" else str(exc)
        }
    )


async def integrity_error_handler(request: Request, exc: IntegrityError):
    """
    Gère les violations d'intégrité (contrainte unique, clé étrangère).
    """
    logger.warning(
        f"Violation d'intégrité sur {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "success": False,
            "code": "INTEGRITY_ERROR",
            "message": "Conflit de données. La ressource existe déjà ou une contrainte est violée.",
            "detail": None if settings.ENVIRONMENT == "production" else str(exc.orig)
        }
    )


async def value_error_handler(request: Request, exc: ValueError):
    """
    Gère les erreurs métier (validation, logique).
    Traduit en 400 Bad Request.
    """
    logger.info(
        f"Erreur métier sur {request.method} {request.url.path}: {exc}"
    )
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "success": False,
            "code": "BUSINESS_ERROR",
            "message": str(exc),
            "detail": str(exc)
        }
    )


async def operational_error_handler(request: Request, exc: OperationalError):
    """
    Gère les erreurs opérationnelles BDD (connexion perdue, timeout).
    """
    logger.error(
        f"Erreur opérationnelle BDD sur {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "code": "DATABASE_UNAVAILABLE",
            "message": "Service temporairement indisponible. Veuillez réessayer.",
            "detail": None
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Gère les exceptions HTTP levées par FastAPI.
    """
    logger.info(
        f"HTTP {exc.status_code} sur {request.method} {request.url.path}: {exc.detail}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "code": f"HTTP_{exc.status_code}",
            "message": exc.detail,
            "detail": None
        }
    )


# ============================================================
# LIFESPAN DE L'APPLICATION
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global scheduler
    
    # Startup
    logger.info("🚀 Démarrage de l'application...")
    app.state.scheduler_running = False
    
    # Initialisation de la base de données
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Connection entre backend et BD réussie avec succès")
    except Exception as e:
        logger.error(f"❌ Connection failed : {e}")
        raise
    
    # Initialiser les schedulers
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        
        # ✅ Créer un scheduler partagé
        scheduler = BackgroundScheduler()
        
        # Initialiser les trois jobs
        scheduler = init_scores_scheduler(scheduler)
        logger.info("✅ Scheduler des scores de fiabilité initialisé")
        
        scheduler = init_alertes_scheduler(scheduler)
        logger.info("✅ Scheduler des alertes VNC initialisé")
        
        scheduler = init_projections_scheduler(scheduler)
        logger.info("✅ Scheduler des projections initialisé")
        
        # Démarrer le scheduler
        scheduler.start()
        app.state.scheduler = scheduler
        app.state.scheduler_running = True
        logger.info("✅ Scheduler global démarré avec succès")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'initialisation du scheduler: {e}")
        app.state.scheduler_running = False
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt de l'application...")
    if scheduler:
        scheduler.shutdown(wait=True)
        logger.info("✅ Scheduler arrêté")
    
    logger.info("🛑 Application arrêtée")


# ============================================================
# CRÉATION DE L'APPLICATION FASTAPI
# ============================================================

app = FastAPI(
    title=settings.APP_NAME,
    description="API de gestion des immobilisations avec OHADA/SYSCOHADA",
    version="1.0.0",
    debug=settings.DEBUG,
    redirect_slashes=False,
    lifespan=lifespan,
)


# ============================================================
# ENREGISTREMENT DES HANDLERS (ORDRE : DU PLUS SPÉCIFIQUE AU PLUS GÉNÉRAL)
# ============================================================

# 1. HTTPException (FastAPI native)
app.add_exception_handler(HTTPException, http_exception_handler)

# 2. Erreurs métier (ValueError)
app.add_exception_handler(ValueError, value_error_handler)

# 3. Violations d'intégrité
app.add_exception_handler(IntegrityError, integrity_error_handler)

# 4. Erreurs opérationnelles BDD
app.add_exception_handler(OperationalError, operational_error_handler)

# 5. Erreurs SQLAlchemy générales
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)

# 6. Exception générique (DOIT être en dernier)
app.add_exception_handler(Exception, global_exception_handler)


# ============================================================
# MIDDLEWARES
# ============================================================

# Ajout des middlewares
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(ApiCollectionSlashMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-CSRF-Token"],
    expose_headers=["*"],
    max_age=3600,
)


# ============================================================
# FICHIERS STATIQUES (BONS DE DÉCAISSEMENT, UPLOADS)
# ============================================================
os.makedirs("static/bons_decaissement", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ============================================================
# INCLUSION DES ROUTERS
# ============================================================

app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(utilisateurs.router, prefix=API_V1_PREFIX)
app.include_router(roles.router, prefix=API_V1_PREFIX)
app.include_router(biens.router, prefix=API_V1_PREFIX)
app.include_router(vehicules.router, prefix=API_V1_PREFIX)
app.include_router(machines.router, prefix=API_V1_PREFIX)
app.include_router(ordinateurs.router, prefix=API_V1_PREFIX)
app.include_router(qr_code.router, prefix=API_V1_PREFIX)
app.include_router(composants.router, prefix=API_V1_PREFIX)
app.include_router(pannes.router, prefix=API_V1_PREFIX)
app.include_router(pieces.router, prefix=API_V1_PREFIX)
app.include_router(besoins.router, prefix=API_V1_PREFIX)
app.include_router(maintenances.router, prefix=API_V1_PREFIX)
app.include_router(validations.router, prefix=API_V1_PREFIX)
app.include_router(amortissements.router, prefix=API_V1_PREFIX)
app.include_router(ecritures_comptables.router, prefix=API_V1_PREFIX)
app.include_router(regles_amortissement.router, prefix=API_V1_PREFIX)
app.include_router(mouvements.router, prefix=API_V1_PREFIX)
app.include_router(notifications.router, prefix=API_V1_PREFIX)
app.include_router(dashboard.router, prefix=API_V1_PREFIX)
app.include_router(audit.router, prefix=API_V1_PREFIX)
app.include_router(rapports.router, prefix=API_V1_PREFIX)
app.include_router(ia_decision.router, prefix=API_V1_PREFIX)
app.include_router(etats.router, prefix=API_V1_PREFIX)
app.include_router(fournitures.router, prefix=API_V1_PREFIX)
app.include_router(cessions.router, prefix=API_V1_PREFIX)
app.include_router(plan_comptable.router, prefix=API_V1_PREFIX)
app.include_router(fournisseurs.router, prefix=API_V1_PREFIX)
app.include_router(localisations.router, prefix=API_V1_PREFIX)
app.include_router(budgets.router, prefix=API_V1_PREFIX)
app.include_router(caisse.router, prefix=API_V1_PREFIX)
app.include_router(mouvements_caisse.router, prefix=API_V1_PREFIX)
app.include_router(pieces_justificatives.router, prefix=API_V1_PREFIX)
app.include_router(etats_financiers.router, prefix=API_V1_PREFIX)


# ============================================================
# ENDPOINTS ROOT ET HEALTH
# ============================================================

@app.get("/", tags=["Root"])
def read_root():
    return {
        "message": "API Gestion des Immobilisations",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Vérification de l'état de l'application."""
    db_status = "unknown"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        db_status = "disconnected"

    jobs_status = {}
    if scheduler:
        jobs = scheduler.get_jobs()
        jobs_status = {
            job.id: {
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "running": job.running if hasattr(job, 'running') else False
            }
            for job in jobs
        }

    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "scheduler": {
            "running": scheduler.running if scheduler else False,
            "jobs": jobs_status
        }
    }


@app.get("/health/database", tags=["Health"])
async def health_database():
    """Vérifie la connectivité à la base de données."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            return {
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Health check BDD échoué: {e}")
        raise HTTPException(
            status_code=503,
            detail="Base de données inaccessible"
        )


@app.get("/health/jobs", tags=["Health"])
async def health_jobs():
    """Vérifie l'état des jobs CRON."""
    jobs_status = []
    if scheduler:
        for job in scheduler.get_jobs():
            jobs_status.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
    
    return {
        "status": "healthy" if scheduler and scheduler.running else "degraded",
        "scheduler_running": scheduler.running if scheduler else False,
        "jobs": jobs_status,
        "timestamp": datetime.utcnow().isoformat()
    }