"""Permissions métier pour les biens immobilisés."""
import logging
from typing import Any, Dict, Optional, Set

from fastapi import Request
from sqlalchemy.orm import Session

from ..models.utilisateur import Utilisateur
from ..models.bien import Bien
from ..models.panne import Panne
from ..schemas.bien import BienUpdate

logger = logging.getLogger(__name__)

FINANCIAL_FIELDS: Set[str] = {
    "prix_acquisition",
    "date_acquisition",
    "cumul_amortissement",
    "cumul_depreciation",
    "statut_comptable",
    "valeur_nette",
    "valeur_comptable",
}

TECHNICIAN_VIEWABLE_ETATS = frozenset({"PANNE", "MAINTENANCE"})

TECHNICIAN_EDITABLE_FIELDS: Set[str] = {
    "etat",
    "localisation",
    "description",
    "image",
    "type_vehicule",
    "marque",
    "modele",
    "immatriculation",
    "poids",
    "dimension",
    "type_carburant",
    "consommation_carburant",
    "consommation_huile",
    "type_propulsion",
    "numero_serie",
    "fabricant",
    "puissance",
    "type_alimentation",
    "tension_normal",
    "service_affecte",
    "responsable",
    "consommation_elec",
    "frequence_maintenance",
    "processeur",
    "ram",
    "stockage",
    "adresse_ip",
    "utilisateur_affecte",
}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "ADMIN": {"view_bien", "edit_bien", "create_bien", "delete_bien", "view_bien_financial", "view_bien_inventory"},
    "DG": {"view_bien", "view_bien_financial", "view_bien_inventory"},
    "GESTIONNAIRE": {"view_bien", "edit_bien", "create_bien", "delete_bien", "view_bien_financial", "view_bien_inventory"},
    "COMPTABLE": {"view_bien", "edit_bien", "create_bien", "view_bien_financial", "view_bien_inventory"},
    "TECHNICIEN": {"view_bien", "edit_bien_limited"},
    "CAISSE": {"view_bien"},
    "MAGASINIER": set(),
    "USER": {"view_bien"},
}


def get_user_role(user: Optional[Utilisateur]) -> str:
    if not user or not user.role:
        return "USER"
    if hasattr(user.role, "nom"):
        return str(user.role.nom).strip().upper()
    return str(user.role).strip().upper()


def _has_permission(user: Optional[Utilisateur], permission: str) -> bool:
    role = get_user_role(user)
    if role == "ADMIN":
        return True
    return permission in ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["USER"])


def can_view_biens(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "view_bien")


def can_view_financial_data(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "view_bien_financial")


def can_view_inventory(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "view_bien_inventory")


def can_create_bien(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "create_bien")


def can_delete_bien(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "delete_bien")


def can_edit_bien_full(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "edit_bien")


def can_edit_bien_technician(user: Optional[Utilisateur]) -> bool:
    return _has_permission(user, "edit_bien_limited")


def can_update_bien(user: Optional[Utilisateur]) -> bool:
    return can_edit_bien_full(user) or can_edit_bien_technician(user)


def _bien_etat_value(bien: Bien) -> str:
    etat = getattr(bien, "etat", None)
    if etat is None:
        return ""
    return etat.value if hasattr(etat, "value") else str(etat).strip().upper()


def can_technician_view_bien(
    user: Utilisateur,
    bien: Bien,
    db: Session,
    panne_id: Optional[int] = None,
) -> bool:
    """Technicien : bien en PANNE/MAINTENANCE ou lié à une de ses pannes."""
    if _bien_etat_value(bien) in TECHNICIAN_VIEWABLE_ETATS:
        return True

    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    user_id = int(user_id)
    bien_id = int(getattr(bien, "id_bien", 0))

    if panne_id is not None:
        try:
            panne_id_int = int(panne_id)
        except (TypeError, ValueError):
            panne_id_int = None
        if panne_id_int is not None:
            panne = (
                db.query(Panne)
                .filter(Panne.id_panne == panne_id_int, Panne.id_bien == bien_id)
                .first()
            )
            if panne is not None:
                if int(panne.id_technicien) == user_id:
                    return True
                # Contexte panne valide : le technicien a au moins une panne sur ce bien
                other = (
                    db.query(Panne)
                    .filter(Panne.id_bien == bien_id, Panne.id_technicien == user_id)
                    .first()
                )
                if other is not None:
                    return True

    assigned = (
        db.query(Panne)
        .filter(Panne.id_bien == bien_id, Panne.id_technicien == user_id)
        .first()
    )
    return assigned is not None


def can_view_bien_detail(
    user: Optional[Utilisateur],
    bien: Bien,
    db: Session,
    panne_id: Optional[int] = None,
) -> bool:
    if not can_view_biens(user):
        return False
    if get_user_role(user) != "TECHNICIEN":
        return True
    return can_technician_view_bien(user, bien, db, panne_id)


def build_bien_context_dict(bien: Bien, user: Optional[Utilisateur]) -> Dict[str, Any]:
    """Résumé non financier d'un bien (contexte panne / fiche technique)."""
    data: Dict[str, Any] = {
        "id_bien": bien.id_bien,
        "type_bien": getattr(bien, "type_bien", None),
        "marque": getattr(bien, "marque", None),
        "fabricant": getattr(bien, "fabricant", None),
        "modele": getattr(bien, "modele", None),
        "numero_serie": getattr(bien, "numero_serie", None),
        "immatriculation": getattr(bien, "immatriculation", None),
        "localisation": getattr(bien, "localisation", None),
        "etat": _bien_etat_value(bien) or None,
        "qr_code": getattr(bien, "qr_code", None),
    }
    return sanitize_bien_dict(data, user)


def log_access_granted(
    user: Optional[Utilisateur],
    action: str,
    *,
    resource_id: Optional[int] = None,
    detail: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    role = get_user_role(user)
    user_id = getattr(user, "id", None)
    ip = request.client.host if request and request.client else None
    logger.info(
        "Accès biens autorisé | action=%s user_id=%s role=%s resource_id=%s ip=%s detail=%s",
        action,
        user_id,
        role,
        resource_id,
        ip,
        detail,
    )


def filter_bien_update(user: Optional[Utilisateur], bien_data: BienUpdate) -> BienUpdate:
    if can_edit_bien_full(user):
        return bien_data

    if not can_edit_bien_technician(user):
        return BienUpdate()

    raw = bien_data.model_dump(exclude_unset=True)
    filtered = {k: v for k, v in raw.items() if k in TECHNICIAN_EDITABLE_FIELDS}

    forbidden = set(raw.keys()) - TECHNICIAN_EDITABLE_FIELDS
    if forbidden:
        log_access_denied(
            user,
            "bien_update_forbidden_fields",
            detail=f"Champs refusés: {sorted(forbidden)}",
        )

    return BienUpdate(**filtered)


def sanitize_bien_dict(data: Dict[str, Any], user: Optional[Utilisateur]) -> Dict[str, Any]:
    if can_view_financial_data(user):
        return data
    sanitized = dict(data)
    for field in FINANCIAL_FIELDS:
        sanitized.pop(field, None)
    return sanitized


def log_access_denied(
    user: Optional[Utilisateur],
    action: str,
    *,
    resource_id: Optional[int] = None,
    detail: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    role = get_user_role(user)
    user_id = getattr(user, "id", None)
    ip = request.client.host if request and request.client else None
    logger.warning(
        "Accès refusé biens | action=%s user_id=%s role=%s resource_id=%s ip=%s detail=%s",
        action,
        user_id,
        role,
        resource_id,
        ip,
        detail,
    )
