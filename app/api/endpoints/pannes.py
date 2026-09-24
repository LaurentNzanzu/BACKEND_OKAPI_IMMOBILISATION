# backend/app/api/endpoints/pannes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import ValidationError

from ...core.database import get_db
# ═══ AJOUT 5.14 — Dépendance module ═══
from ...core.dependencies_modules import require_module
# ═══ FIN AJOUT 5.14 ═══
from ...schemas.panne import PanneCreate, PanneUpdate, PanneResponse
from ...services.panne_service import PanneService, panne_to_response
from ...services.bien_service import BienService
from ...core.bien_permissions import build_bien_context_dict
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.panne import StatutPanne
from ...models.bien import Bien

# ═══ MODIF 5.14 — require_module sur le router ═══
router = APIRouter(
    prefix="/pannes",
    tags=["Pannes"],
    dependencies=[Depends(require_module("MAINTENANCE"))],
)
# ═══ FIN MODIF 5.14 ═══


def check_panne_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role == "ADMIN":
        return True
    if role == "DG" and action in ["view", "create", "update"]:
        return True
    if role == "TECHNICIEN" and action in ["view", "create", "update"]:
        return True
    if role == "COMPTABLE" and action == "view":
        return True
    if role == "MAGASINIER" and action == "view":
        return True
    if role == "GESTIONNAIRE" and action == "view":
        return True
    if role == "CAISSE" and action == "view":
        return True
    return False


# ═══ AJOUT 5.14 — Helpers d'isolation multi-tenant ═══
def _is_platform_admin(user: Utilisateur) -> bool:
    return bool(getattr(user, "is_platform_admin", False))


def _get_organisation_id_bien(db: Session, bien_id: int) -> Optional[int]:
    """Retourne l'organisation_id d'un Bien."""
    if bien_id is None:
        return None
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    return getattr(bien, "organisation_id", None) if bien else None


def _check_acces_bien_id(db: Session, current_user: Utilisateur, bien_id: int, label: str = "bien") -> None:
    """Vérifie l'accès via bien_id. Lève 403 si interdit."""
    if _is_platform_admin(current_user):
        return
    org_id = _get_organisation_id_bien(db, bien_id)
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accès refusé : {label} #{bien_id} sans organisation (donnée historique).",
        )
    if org_id != current_user.organisation_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accès refusé : {label} #{bien_id} appartient à une autre organisation.",
        )


def _check_acces_panne(db: Session, current_user: Utilisateur, panne) -> None:
    """Vérifie l'accès à une Panne via son bien."""
    _check_acces_bien_id(db, current_user, getattr(panne, "id_bien", None), "panne")
# ═══ FIN AJOUT 5.14 ═══


def _serialize_panne(panne, current_user: Utilisateur, db: Session) -> PanneResponse:
    response = panne_to_response(panne)
    bien_service = BienService(db)
    bien = bien_service.get_bien_by_id(panne.id_bien)
    if bien:
        response.bien_context = build_bien_context_dict(bien, current_user)
    return response


@router.post("/", response_model=PanneResponse, status_code=status.HTTP_201_CREATED)
async def declarer_panne(
    data: PanneCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not check_panne_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.14 — Vérification d'accès sur le bien ciblé ═══
    _check_acces_bien_id(db, current_user, data.id_bien, "bien")
    # ═══ FIN MODIF 5.14 ═══

    service = PanneService(db)
    audit_service = AuditService(db)

    try:
        panne = service.declarer_panne(data, current_user.id)

        audit_service.log_create(
            user_id=current_user.id,
            table_name="pannes",
            record_id=panne.id_panne,
            new_values={
                "id_bien": data.id_bien,
                "type_panne": data.type_panne.value,
                "diagnostic": data.diagnostic,
                "statut": panne.statut.value if panne.statut else None,
            },
            request=request,
        )

        return _serialize_panne(panne, current_user, db)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bien/{bien_id}", response_model=List[PanneResponse])
async def get_pannes_by_bien(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.14 — Vérification d'accès sur le bien ═══
    _check_acces_bien_id(db, current_user, bien_id, "bien")
    # ═══ FIN MODIF 5.14 ═══

    service = PanneService(db)
    pannes = service.get_pannes_by_bien(bien_id)
    return [_serialize_panne(p, current_user, db) for p in pannes]


@router.get("/mes-pannes", response_model=List[PanneResponse])
async def get_mes_pannes(
    statut: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    if current_user.role.nom.upper() == "TECHNICIEN":
        pannes = service.get_pannes_by_technicien(current_user.id, statut)
    else:
        pannes = service.get_pannes_actives()

    # ═══ MODIF 5.14 — Filtre ONG post-query ═══
    if not _is_platform_admin(current_user):
        org_id = current_user.organisation_id
        bien_ids_ok = {
            b.id_bien
            for b in db.query(Bien.id_bien)
            .filter(Bien.organisation_id == org_id)
            .all()
        }
        pannes = [p for p in pannes if p.id_bien in bien_ids_ok]
    # ═══ FIN MODIF 5.14 ═══

    return [_serialize_panne(p, current_user, db) for p in pannes]


@router.get("/actives", response_model=List[PanneResponse])
async def get_pannes_actives(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    pannes = service.get_pannes_actives()

    # ═══ MODIF 5.14 — Filtre ONG post-query ═══
    if not _is_platform_admin(current_user):
        org_id = current_user.organisation_id
        bien_ids_ok = {
            b.id_bien
            for b in db.query(Bien.id_bien)
            .filter(Bien.organisation_id == org_id)
            .all()
        }
        pannes = [p for p in pannes if p.id_bien in bien_ids_ok]
    # ═══ FIN MODIF 5.14 ═══

    return [_serialize_panne(p, current_user, db) for p in pannes]


@router.get("/{panne_id}", response_model=PanneResponse)
async def get_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PanneService(db)
    panne = service.get_panne(panne_id)
    if not panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    # ═══ MODIF 5.14 — Vérification d'accès ONG ═══
    _check_acces_panne(db, current_user, panne)
    # ═══ FIN MODIF 5.14 ═══

    return _serialize_panne(panne, current_user, db)


@router.put("/{panne_id}", response_model=PanneResponse)
async def update_panne(
    panne_id: int,
    data: PanneUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not check_panne_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = PanneService(db)
    audit_service = AuditService(db)

    old_panne = service.get_panne(panne_id)
    if not old_panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    # ═══ MODIF 5.14 — Vérification d'accès ONG ═══
    _check_acces_panne(db, current_user, old_panne)
    # ═══ FIN MODIF 5.14 ═══

    panne = service.update_panne(panne_id, data)
    if not panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    audit_service.log_update(
        user_id=current_user.id,
        table_name="pannes",
        record_id=panne_id,
        old_values={
            "statut": old_panne.statut.value if old_panne.statut else None,
            "diagnostic": old_panne.diagnostic,
        },
        new_values={
            "statut": panne.statut.value if panne.statut else None,
            "diagnostic": panne.diagnostic,
        },
        request=request,
    )

    return _serialize_panne(panne, current_user, db)


@router.patch("/{panne_id}/statut", response_model=PanneResponse)
async def changer_statut_panne(
    panne_id: int,
    statut: StatutPanne,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not check_panne_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = PanneService(db)
    audit_service = AuditService(db)

    old_panne = service.get_panne(panne_id)
    if not old_panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    # ═══ MODIF 5.14 — Vérification d'accès ONG ═══
    _check_acces_panne(db, current_user, old_panne)
    # ═══ FIN MODIF 5.14 ═══

    panne = service.changer_statut(panne_id, statut)
    if not panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    audit_service.log_update(
        user_id=current_user.id,
        table_name="pannes",
        record_id=panne_id,
        old_values={"statut": old_panne.statut.value if old_panne.statut else None},
        new_values={"statut": statut.value},
        request=request,
    )

    return _serialize_panne(panne, current_user, db)


@router.post("/{panne_id}/resoudre", response_model=PanneResponse)
async def resoudre_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not check_panne_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    if current_user.role.nom.upper() != "TECHNICIEN":
        raise HTTPException(status_code=403, detail="Seul un technicien peut résoudre une panne")

    service = PanneService(db)
    old_panne = service.get_panne(panne_id)
    if not old_panne:
        raise HTTPException(status_code=404, detail="Panne non trouvée")

    # ═══ MODIF 5.14 — Vérification d'accès ONG ═══
    _check_acces_panne(db, current_user, old_panne)
    # ═══ FIN MODIF 5.14 ═══

    try:
        panne = service.resoudre_panne(panne_id, current_user.id)
        return _serialize_panne(panne, current_user, db)
    except ValueError as e:
        if "non trouvée" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/statistiques/summary")
async def get_pannes_statistiques(
    bien_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_panne_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.14 — Si bien_id fourni, vérifier l'accès ; sinon filtrer par ONG ═══
    if bien_id is not None:
        _check_acces_bien_id(db, current_user, bien_id, "bien")
    # ═══ FIN MODIF 5.14 ═══

    service = PanneService(db)
    return service.get_statistiques(bien_id)