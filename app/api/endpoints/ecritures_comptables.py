# backend/app/api/endpoints/ecritures_comptables.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from ...core.database import get_db
# ═══ AJOUT 5.20 — Dépendance module ═══
from ...core.dependencies_modules import require_module
# ═══ FIN AJOUT 5.20 ═══
from ...schemas.ecriture_comptable import EcritureResponse
from ...services.comptabilite_service import ComptabiliteService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...models.ecriture_comptable import (
    EcritureComptable,
    StatutEcriture,
    TypeOperationEnum,
)

# ═══ MODIF 5.20 — require_module sur le router ═══
router = APIRouter(
    prefix="/ecritures",
    tags=["Ecritures Comptables"],
    dependencies=[Depends(require_module("IMMOBILISATION"))],
)
# ═══ FIN MODIF 5.20 ═══


def check_ecriture_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "COMPTABLE", "DG"]


def _get_bien_designation(bien: Optional[Bien]) -> str:
    if not bien:
        return f"Bien #{None}"
    marque = ''; modele = ''
    if bien.attributs_specifiques:
        marque = bien.attributs_specifiques.get('marque', '')
        modele = bien.attributs_specifiques.get('modele', '')
    if not marque:
        try:
            marque = getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''
        except Exception:
            marque = ''
    if not modele:
        try:
            modele = getattr(bien, 'modele', None) or ''
        except Exception:
            modele = ''
    designation = f"{marque} {modele}".strip()
    return designation if designation else f"Bien #{bien.id_bien}"


# ═══ AJOUT 5.20 — Helpers d'isolation multi-tenant ═══
def _is_platform_admin(user: Utilisateur) -> bool:
    return bool(getattr(user, "is_platform_admin", False))


def _check_acces_bien_id(db: Session, current_user: Utilisateur, bien_id: int) -> Bien:
    """
    Vérifie l'accès à un Bien par son ID.
    Retourne le bien si autorisé, lève 403 sinon.
    """
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(status_code=404, detail=f"Bien #{bien_id} non trouvé")

    if _is_platform_admin(current_user):
        return bien

    bien_org = getattr(bien, "organisation_id", None)
    if bien_org is None:
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : bien #{bien_id} sans organisation (donnée historique).",
        )
    if bien_org != current_user.organisation_id:
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : bien #{bien_id} appartient à une autre organisation.",
        )
    return bien


def _check_acces_ecriture(db: Session, current_user: Utilisateur, ecriture: EcritureComptable) -> None:
    """Vérifie l'accès à une écriture comptable."""
    if _is_platform_admin(current_user):
        return

    ecriture_org = getattr(ecriture, "organisation_id", None)
    if ecriture_org is not None:
        if ecriture_org != current_user.organisation_id:
            raise HTTPException(
                status_code=403,
                detail=f"Accès refusé : écriture #{ecriture.id_ecriture} appartient à une autre organisation.",
            )
        return

    # Fallback (cas théorique) : vérifier via le Bien
    _check_acces_bien_id(db, current_user, ecriture.id_bien)


def _get_organisation_filter(current_user: Utilisateur) -> Optional[int]:
    """Retourne l'organisation_id à filtrer (None pour admin plateforme)."""
    if _is_platform_admin(current_user):
        return None
    return current_user.organisation_id
# ═══ FIN AJOUT 5.20 ═══


@router.get("/non-validees", response_model=List[EcritureResponse])
async def get_ecritures_en_attente(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.20 — Filtre ONG ═══
    org_filter = _get_organisation_filter(current_user)
    # ═══ FIN MODIF 5.20 ═══

    service = ComptabiliteService(db, cree_par_id=current_user.id)
    ecritures = service.get_ecritures_en_attente(organisation_id=org_filter)

    for ecriture in ecritures:
        bien = db.query(Bien).filter(Bien.id_bien == ecriture.id_bien).first()
        if bien:
            ecriture.bien_designation = _get_bien_designation(bien)
    return ecritures


@router.get("/bien/{bien_id}", response_model=List[EcritureResponse])
async def get_ecritures_by_bien(
    bien_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.20 — Vérification d'accès sur le bien ═══
    bien = _check_acces_bien_id(db, current_user, bien_id)
    # ═══ FIN MODIF 5.20 ═══

    ecritures = (
        db.query(EcritureComptable)
        .filter(EcritureComptable.id_bien == bien_id)
        .order_by(EcritureComptable.date_ecriture.desc())
        .limit(limit)
        .all()
    )
    for ecriture in ecritures:
        ecriture.bien_designation = _get_bien_designation(bien)
    return ecritures


@router.get("", response_model=List[EcritureResponse])
@router.get("/", response_model=List[EcritureResponse], include_in_schema=False)
async def get_all_ecritures(
    skip: int = 0,
    limit: int = 100,
    type_operation: Optional[str] = Query(None),
    date_debut: Optional[str] = Query(None),
    date_fin: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    query = db.query(EcritureComptable).order_by(EcritureComptable.date_ecriture.desc())

    # ═══ MODIF 5.20 — Filtre ONG ═══
    org_filter = _get_organisation_filter(current_user)
    if org_filter is not None:
        query = query.filter(EcritureComptable.organisation_id == org_filter)
    # ═══ FIN MODIF 5.20 ═══

    if type_operation:
        try:
            query = query.filter(EcritureComptable.type_operation == TypeOperationEnum(type_operation))
        except ValueError:
            pass
    if date_debut:
        try:
            query = query.filter(EcritureComptable.date_ecriture >= datetime.strptime(date_debut, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_fin:
        try:
            query = query.filter(EcritureComptable.date_ecriture <= datetime.strptime(date_fin, "%Y-%m-%d"))
        except ValueError:
            pass
    if statut:
        try:
            query = query.filter(EcritureComptable.statut == StatutEcriture(statut))
        except ValueError:
            pass

    ecritures = query.offset(skip).limit(limit).all()
    for ecriture in ecritures:
        bien = db.query(Bien).filter(Bien.id_bien == ecriture.id_bien).first()
        if bien:
            ecriture.bien_designation = _get_bien_designation(bien)
    return ecritures


@router.get("/export-csv")
async def exporter_ecritures_csv(
    type_operation: Optional[str] = Query(None),
    date_debut: Optional[str] = Query(None),
    date_fin: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    query = db.query(EcritureComptable).order_by(EcritureComptable.date_ecriture.desc())

    # ═══ MODIF 5.20 — Filtre ONG ═══
    org_filter = _get_organisation_filter(current_user)
    if org_filter is not None:
        query = query.filter(EcritureComptable.organisation_id == org_filter)
    # ═══ FIN MODIF 5.20 ═══

    if type_operation:
        try:
            query = query.filter(EcritureComptable.type_operation == TypeOperationEnum(type_operation))
        except ValueError:
            pass
    if date_debut:
        try:
            query = query.filter(EcritureComptable.date_ecriture >= datetime.strptime(date_debut, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_fin:
        try:
            query = query.filter(EcritureComptable.date_ecriture <= datetime.strptime(date_fin, "%Y-%m-%d"))
        except ValueError:
            pass
    if statut:
        try:
            query = query.filter(EcritureComptable.statut == StatutEcriture(statut))
        except ValueError:
            pass

    ecritures = query.all()

    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Compte Débit", "Compte Crédit", "Montant", "Libellé", "Type", "Statut", "Bien"])
    for e in ecritures:
        bien = db.query(Bien).filter(Bien.id_bien == e.id_bien).first()
        designation = _get_bien_designation(bien) if bien else ""
        writer.writerow([
            e.date_ecriture.strftime("%Y-%m-%d") if e.date_ecriture else "",
            e.compte_debit, e.compte_credit, f"{e.montant:.2f}", e.libelle or "",
            e.type_operation.value if hasattr(e.type_operation, 'value') else str(e.type_operation),
            e.statut.value if hasattr(e.statut, 'value') else str(e.statut),
            designation
        ])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ecritures_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


@router.post("/{id_ecriture}/valider", response_model=EcritureResponse)
async def valider_ecriture(
    id_ecriture: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.20 — Vérification d'accès ═══
    ecriture_obj = db.query(EcritureComptable).filter(EcritureComptable.id_ecriture == id_ecriture).first()
    if not ecriture_obj:
        raise HTTPException(status_code=404, detail="Écriture non trouvée")
    _check_acces_ecriture(db, current_user, ecriture_obj)
    # ═══ FIN MODIF 5.20 ═══

    service = ComptabiliteService(db, cree_par_id=current_user.id)
    ecriture = service.valider_ecriture(id_ecriture, current_user.id)
    if not ecriture:
        raise HTTPException(status_code=404, detail="Écriture non trouvée")

    bien = db.query(Bien).filter(Bien.id_bien == ecriture.id_bien).first()
    if bien:
        ecriture.bien_designation = _get_bien_designation(bien)
    return ecriture


@router.put("/{id_ecriture}", response_model=EcritureResponse)
async def update_ecriture_comptable(
    id_ecriture: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    ecriture = db.query(EcritureComptable).filter(EcritureComptable.id_ecriture == id_ecriture).first()
    if not ecriture:
        raise HTTPException(status_code=404, detail="Écriture non trouvée")

    # ═══ MODIF 5.20 — Vérification d'accès ═══
    _check_acces_ecriture(db, current_user, ecriture)
    # ═══ FIN MODIF 5.20 ═══

    if ecriture.validee or ecriture.verrouille_definitivement:
        raise HTTPException(status_code=400, detail="Impossible de modifier une écriture validée ou verrouillée définitivement.")

    if "montant" in data:
        ecriture.montant = float(data["montant"])
    if "motif_modification" in data and data["motif_modification"]:
        ecriture.motif_modification = data["motif_modification"]

    ecriture.date_modification = datetime.utcnow()
    ecriture.id_modificateur = current_user.id

    db.commit()
    db.refresh(ecriture)

    bien = db.query(Bien).filter(Bien.id_bien == ecriture.id_bien).first()
    if bien:
        ecriture.bien_designation = _get_bien_designation(bien)
    return ecriture


@router.post("/reprise-depreciation", status_code=status.HTTP_201_CREATED)
async def reprise_depreciation(
    data: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.20 — Vérification d'accès sur le bien ═══
    bien_id = data.get("bien_id")
    if not bien_id:
        raise HTTPException(status_code=400, detail="bien_id est obligatoire")
    _check_acces_bien_id(db, current_user, bien_id)
    # ═══ FIN MODIF 5.20 ═══

    try:
        service = ComptabiliteService(db, cree_par_id=current_user.id)
        result = service.reprendre_depreciation(
            bien_id=bien_id,
            montant_reprise=float(data["montant_reprise"]),
            motif=data.get("motif", ""),
            depreciation_id=data.get("depreciation_id"),
        )
        ecriture = result["ecriture"]
        bien = db.query(Bien).filter(Bien.id_bien == ecriture.id_bien).first()
        if bien:
            ecriture.bien_designation = _get_bien_designation(bien)
        return {
            "ecriture": ecriture,
            "nouveau_cumul_depreciation": result["nouveau_cumul_depreciation"],
            "statut_comptable": result["statut_comptable"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/journal-export")
async def get_journal_quotidien(
    date: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    try:
        from datetime import timedelta
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        debut_jour = datetime.combine(date_obj, datetime.min.time())
        fin_jour = debut_jour + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide. Utilisez YYYY-MM-DD")

    query = db.query(EcritureComptable).filter(
        EcritureComptable.type_operation == TypeOperationEnum.DOTATION_AMORTISSEMENT,
        EcritureComptable.date_ecriture >= debut_jour,
        EcritureComptable.date_ecriture < fin_jour,
        EcritureComptable.statut == StatutEcriture.VALIDEE,
    )

    # ═══ MODIF 5.20 — Filtre ONG ═══
    org_filter = _get_organisation_filter(current_user)
    if org_filter is not None:
        query = query.filter(EcritureComptable.organisation_id == org_filter)
    # ═══ FIN MODIF 5.20 ═══

    ecritures = query.order_by(EcritureComptable.id_ecriture).all()

    result = []
    for e in ecritures:
        bien = db.query(Bien).filter(Bien.id_bien == e.id_bien).first()
        result.append({
            "numero_piece": f"OD-{e.id_ecriture:06d}" if e.journal == "OD" else f"{e.journal or 'ECR'}-{e.id_ecriture:06d}",
            "date": e.date_ecriture.strftime("%Y-%m-%d") if e.date_ecriture else None,
            "compte_debit": e.compte_debit,
            "compte_credit": e.compte_credit,
            "montant": e.montant,
            "libelle": e.libelle,
            "bien_reference": _get_bien_designation(bien) if bien else None
        })
    return result