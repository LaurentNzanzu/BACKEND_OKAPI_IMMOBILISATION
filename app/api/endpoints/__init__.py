from typing import Optional, Dict
from fastapi import APIRouter
from .biens import router as biens_router
from .vehicules import router as vehicules_router
from .machines import router as machines_router
from .ordinateurs import router as ordinateurs_router
from .qr_code import router as qr_code_router
from .composants import router as composants_router
from .pannes import router as pannes_router
from .pieces import router as pieces_router
from .besoins import router as besoins_router
from .maintenances import router as maintenances_router
from .amortissements import router as amortissements_router
from .ecritures_comptables import router as ecritures_comptables_router
from .regles_amortissement import router as regles_amortissement_router
from .dashboard import router as dashboard_router
from .notifications import router as notifications_router
from .audit import router as audit_router
from .rapports import router as rapports_router
from .ia_decision import router as ia_decision_router
from .etats import router as etats_router 
from .fournisseurs import router as fournisseurs_router
from .plan_comptable import router as plan_comptable_router
from .utilisateurs import router as utilisateurs_router
from .roles import router as roles_router
from .auth import router as auth_router


AVAILABLE_ROUTERS: list[str] = [
    "biens",
    "vehicules",
    "machines",
    "ordinateurs",
    "qr_code",
    "composants",
    "pannes",
    "pieces",
    "besoins",
    "maintenances",
    "amortissements",
    "ecritures_comptables",
    "regles_amortissement",
    "dashboard",
    "notifications",
    "audit",
    "rapports",
     "ia_decision",
     "etats",
     "fournisseurs",
     "plan_comptable",
     "utilisateurs",
     "roles",
     "auth"
]

def get_router(name: str) -> Optional[APIRouter]:
    if name not in AVAILABLE_ROUTERS:
        return None

    try:
        module = __import__(
            f"app.api.endpoints.{name}",
            fromlist=["router"]
        )
        return getattr(module, "router", None)
    except (ImportError, AttributeError):
        return None

def get_all_active_routers() -> Dict[str, APIRouter]:
    routers = {}
    for name in AVAILABLE_ROUTERS:
        router = get_router(name)
        if router is not None:
            routers[name] = router
    return routers

def register_routers(app, prefix: str = "/api/v1"):
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        raise TypeError("L'argument 'app' doit être une instance de FastAPI")

    active_routers = get_all_active_routers()

    for name, router in active_routers.items():
        app.include_router(router, prefix=prefix)

__all__ = [
    "AVAILABLE_ROUTERS",
    "get_router",
    "get_all_active_routers",
    "register_routers",
    "biens_router",
    "pannes_router",
    "pieces_router",
    "besoins_router",
    "composants_router",
    "vehicules_router",
    "machines_router",
    "ordinateurs_router",
    "qr_code_router",
    "maintenances_router",
    "amortissements_router",
    "ecritures_comptables_router",
    "regles_amortissement_router",
    "dashboard_router",
    "notifications_router",
    "audit_router",
    "rapports_router",
    "ia_decision_router",
    "etats_router",
    "fournisseurs_router",
    "plan_comptable_router",
    "utilisateurs_router",
    "roles_router",
    "auth_router"
]
