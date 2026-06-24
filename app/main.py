# coding: utf-8
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.database import engine, Base
from app.core.config import settings

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
    fournisseurs



)

app = FastAPI(
    title=settings.APP_NAME,
    description="API de gestion des immobilisations",
    version="1.0.0",
    debug=settings.DEBUG,
    redirect_slashes=False,
)

_API_COLLECTION_PATH = re.compile(r"^/api/v1/[^/]+$")


class ApiCollectionSlashMiddleware(BaseHTTPMiddleware):
    """Accepte les URLs de collection sans slash final (redirect_slashes désactivé)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _API_COLLECTION_PATH.match(path):
            request.scope["path"] = f"{path}/"
            request.scope["raw_path"] = f"{path}/".encode("latin-1")
        return await call_next(request)

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
#reader
#message de la creation de la base de donnees 
@app.on_event("startup")
def init_database():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Connection entre backend et BD reussi  avec succès")
    except Exception as e:
        print(f"❌ Connection failed : {e}")
        raise

API_V1_PREFIX = "/api/v1"

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
    db_status = "unknown"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "database": db_status
    }