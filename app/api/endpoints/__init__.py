# backend/app/api/endpoints/__init__.py
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
from .budgets import router as budgets_router  # NOUVEAU
from .validations import router as validations_router  # MODIFIÉ
from .mouvements_caisse import router as mouvements_caisse_router
from .pieces_justificatives import router as pieces_justificatives_router
from .concertations import router as concertations_router



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
    "auth",
    "budgets",  # NOUVEAU
    "validations",  # MODIFIÉ
    "mouvements_caisse",
    "pieces_justificatives",
    "concertations",
]


def get_router(name: str):
    """Récupère un routeur par son nom"""
    if name not in AVAILABLE_ROUTERS:
        return None
    
    routers = {
        "biens": biens_router,
        "vehicules": vehicules_router,
        "machines": machines_router,
        "ordinateurs": ordinateurs_router,
        "qr_code": qr_code_router,
        "composants": composants_router,
        "pannes": pannes_router,
        "pieces": pieces_router,
        "besoins": besoins_router,
        "maintenances": maintenances_router,
        "amortissements": amortissements_router,
        "ecritures_comptables": ecritures_comptables_router,
        "regles_amortissement": regles_amortissement_router,
        "dashboard": dashboard_router,
        "notifications": notifications_router,
        "audit": audit_router,
        "rapports": rapports_router,
        "ia_decision": ia_decision_router,
        "etats": etats_router,
        "fournisseurs": fournisseurs_router,
        "plan_comptable": plan_comptable_router,
        "utilisateurs": utilisateurs_router,
        "roles": roles_router,
        "auth": auth_router,
        "budgets": budgets_router,
        "validations": validations_router,
        "mouvements_caisse": mouvements_caisse_router,
        "pieces_justificatives": pieces_justificatives_router,
        "concertations": concertations_router,
    }
    return routers.get(name)


def get_all_active_routers():
    """Récupère tous les routeurs actifs"""
    routers = {}
    for name in AVAILABLE_ROUTERS:
        router = get_router(name)
        if router is not None:
            routers[name] = router
    return routers


def register_routers(app, prefix: str = "/api/v1"):
    """Enregistre tous les routeurs sur l'application FastAPI"""
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
    "auth_router",
    "budgets_router",
    "validations_router",
    "mouvements_caisse_router",
    "pieces_justificatives_router",
    "concertations_router",
]