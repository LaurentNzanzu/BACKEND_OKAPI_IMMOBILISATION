
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ModuleCode(str, Enum):
    """Codes des 18 modules SaaS (identifiants stables — NE PAS renommer)."""
    IMMOBILISATION = "IMMOBILISATION"
    MAINTENANCE = "MAINTENANCE"
    VEHICULE = "VEHICULE"
    CHAUFFEUR = "CHAUFFEUR"
    MISSION = "MISSION"
    CARBURANT = "CARBURANT"
    IMPORT_CSV = "IMPORT_CSV"
    PROJET = "PROJET"
    TRAJET = "TRAJET"
    INCIDENT = "INCIDENT"
    WORKFLOW_PERSONNALISE = "WORKFLOW_PERSONNALISE"
    ALERTES_AUTOMATIQUES = "ALERTES_AUTOMATIQUES"
    MOBILE_PWA = "MOBILE_PWA"
    GPS_TRACKING = "GPS_TRACKING"
    REPORTING_AVANCE = "REPORTING_AVANCE"
    IOT_TELEMETRIE = "IOT_TELEMETRIE"
    MULTI_DEVISES = "MULTI_DEVISES"
    API_EXTERNE = "API_EXTERNE"


# Référentiel complet : code → métadonnées (libellé, description, icône Heroicons)
MODULES_DISPONIBLES: Dict[str, Dict[str, str]] = {
    "IMMOBILISATION": {
        "libelle": "Immobilisations",
        "description": "Gestion des biens et du patrimoine",
        "icone": "CubeIcon",
    },
    "MAINTENANCE": {
        "libelle": "Maintenances",
        "description": "Planification et suivi des maintenances",
        "icone": "WrenchScrewdriverIcon",
    },
    "VEHICULE": {
        "libelle": "Véhicules",
        "description": "Gestion du parc automobile",
        "icone": "TruckIcon",
    },
    "CHAUFFEUR": {
        "libelle": "Chauffeurs",
        "description": "Gestion des chauffeurs et permis",
        "icone": "UserIcon",
    },
    "MISSION": {
        "libelle": "Missions",
        "description": "Demande, validation et suivi des missions",
        "icone": "MapPinIcon",
    },
    "CARBURANT": {
        "libelle": "Carburant",
        "description": "Ravitaillements et consommation",
        "icone": "BanknotesIcon",
    },
    "IMPORT_CSV": {
        "libelle": "Import CSV",
        "description": "Import de données depuis Excel/CSV",
        "icone": "ArrowUpTrayIcon",
    },
    "PROJET": {
        "libelle": "Projets bailleurs",
        "description": "Gestion des projets et budgets bailleurs",
        "icone": "FolderOpenIcon",
    },
    "TRAJET": {
        "libelle": "Trajets",
        "description": "Suivi des trajets opérationnels",
        "icone": "ArrowRightIcon",
    },
    "INCIDENT": {
        "libelle": "Incidents",
        "description": "Déclaration d'incidents et pannes",
        "icone": "ExclamationTriangleIcon",
    },
    "WORKFLOW_PERSONNALISE": {
        "libelle": "Workflow personnalisé",
        "description": "Configuration des circuits de validation par ONG",
        "icone": "AdjustmentsHorizontalIcon",
    },
    "ALERTES_AUTOMATIQUES": {
        "libelle": "Alertes automatiques",
        "description": "Alertes temps réel (vitesse, zones, carburant)",
        "icone": "BellAlertIcon",
    },
    "MOBILE_PWA": {
        "libelle": "PWA chauffeur",
        "description": "Application mobile offline-first pour chauffeurs",
        "icone": "ComputerDesktopIcon",
    },
    "GPS_TRACKING": {
        "libelle": "GPS mobile",
        "description": "Suivi GPS via le téléphone du chauffeur",
        "icone": "MapPinIcon",
    },
    "REPORTING_AVANCE": {
        "libelle": "Rapports avancés",
        "description": "Rapports et exports pour bailleurs",
        "icone": "DocumentChartBarIcon",
    },
    "IOT_TELEMETRIE": {
        "libelle": "Boîtiers IoT",
        "description": "Intégration des boîtiers GPS physiques",
        "icone": "CpuChipIcon",
    },
    "MULTI_DEVISES": {
        "libelle": "Multi-devises",
        "description": "Gestion USD / CDF / autres devises",
        "icone": "CurrencyDollarIcon",
    },
    "API_EXTERNE": {
        "libelle": "API externe",
        "description": "API pour intégrations tierces",
        "icone": "LinkIcon",
    },
}


# Cartographie plan d'abonnement → modules par défaut
MODULES_PAR_PLAN: Dict[str, List[str]] = {
    "BASIC": [
        "IMMOBILISATION",
        "MAINTENANCE",
        "VEHICULE",
        "CHAUFFEUR",
        "MISSION",
        "CARBURANT",
        "IMPORT_CSV",
    ],
    "PRO": [
        # BASIC +
        "IMMOBILISATION",
        "MAINTENANCE",
        "VEHICULE",
        "CHAUFFEUR",
        "MISSION",
        "CARBURANT",
        "IMPORT_CSV",
        # PRO spécifique
        "PROJET",
        "TRAJET",
        "INCIDENT",
        "WORKFLOW_PERSONNALISE",
        "ALERTES_AUTOMATIQUES",
        "MOBILE_PWA",
        "GPS_TRACKING",
        "REPORTING_AVANCE",
    ],
    "ENTERPRISE": [
        # Tous les 18 modules
        "IMMOBILISATION",
        "MAINTENANCE",
        "VEHICULE",
        "CHAUFFEUR",
        "MISSION",
        "CARBURANT",
        "IMPORT_CSV",
        "PROJET",
        "TRAJET",
        "INCIDENT",
        "WORKFLOW_PERSONNALISE",
        "ALERTES_AUTOMATIQUES",
        "MOBILE_PWA",
        "GPS_TRACKING",
        "REPORTING_AVANCE",
        "IOT_TELEMETRIE",
        "MULTI_DEVISES",
        "API_EXTERNE",
    ],
}


def get_modules_pour_plan(plan: str) -> List[str]:
    """
    Retourne la liste des codes de modules activés par défaut pour un plan.

    Args:
        plan: "BASIC", "PRO" ou "ENTERPRISE" (insensible à la casse)

    Returns:
        Liste des codes modules (fallback BASIC si plan inconnu)
    """
    if not plan:
        return list(MODULES_PAR_PLAN["BASIC"])
    plan_upper = str(plan).upper().strip()
    return list(MODULES_PAR_PLAN.get(plan_upper, MODULES_PAR_PLAN["BASIC"]))


def module_existe(module_code: str) -> bool:
    """Vérifie qu'un code module est valide (existe dans le référentiel)."""
    if not module_code:
        return False
    return str(module_code).strip().upper() in MODULES_DISPONIBLES


def normaliser_modules(modules: List[str]) -> List[str]:
    """
    Normalise une liste de codes modules :
    - Trim + uppercase
    - Supprime les doublons
    - Filtre les codes invalides (avec log d'avertissement)
    """
    if not modules:
        return []
    result: List[str] = []
    seen = set()
    for m in modules:
        if not m:
            continue
        code = str(m).strip().upper()
        if not code:
            continue
        if code not in seen and module_existe(code):
            seen.add(code)
            result.append(code)
        elif not module_existe(code):
            logger.warning(f"Module inconnu ignoré : '{code}'")
    return result


def get_module_info(module_code: str) -> Optional[Dict[str, str]]:
    """Retourne les métadonnées d'un module (libellé, description, icône)."""
    if not module_code:
        return None
    return MODULES_DISPONIBLES.get(str(module_code).strip().upper())


def lister_tous_modules() -> List[Dict[str, str]]:
    """Retourne la liste complète des modules avec leurs métadonnées."""
    return [
        {"code": code, **info}
        for code, info in MODULES_DISPONIBLES.items()
    ]