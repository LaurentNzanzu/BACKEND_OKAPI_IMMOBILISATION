# backend/app/api/endpoints/ecritures_comptables.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from ...core.database import get_db
from ...schemas.ecriture_comptable import EcritureResponse
from ...services.comptabilite_service import ComptabiliteService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...models.ecriture_comptable import EcritureComptable, StatutEcriture

router = APIRouter(prefix="/ecritures", tags=["Ecritures Comptables"])

def check_ecriture_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "COMPTABLE", "DG"]

def _get_bien_designation(bien: Optional[Bien]) -> str:
    if not bien:
        return f"Bien #{None}"
    marque = getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''
    modele = getattr(bien, 'modele', None) or ''
    designation = f"{marque} {modele}".strip()
    return designation if designation else f"Bien #{bien.id_bien}"


@router.get("/non-validees", response_model=List[EcritureResponse])
async def get_ecritures_en_attente(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ComptabiliteService(db, cree_par_id=current_user.id)
    ecritures = service.get_ecritures_en_attente()
    
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

    ecritures = (
        db.query(EcritureComptable)
        .filter(EcritureComptable.id_bien == bien_id)
        .order_by(EcritureComptable.date_ecriture.desc())
        .limit(limit)
        .all()
    )

    for ecriture in ecritures:
        bien = db.query(Bien).filter(Bien.id_bien == ecriture.id_bien).first()
        if bien:
            ecriture.bien_designation = _get_bien_designation(bien)

    return ecritures


@router.get("", response_model=List[EcritureResponse])
@router.get("/", response_model=List[EcritureResponse], include_in_schema=False)
async def get_all_ecritures(
    skip: int = 0,
    limit: int = 100,
    type_operation: Optional[str] = Query(None, description="Filtrer par type d'opération"),
    date_debut: Optional[str] = Query(None, description="Date de début (YYYY-MM-DD)"),
    date_fin: Optional[str] = Query(None, description="Date de fin (YYYY-MM-DD)"),
    statut: Optional[str] = Query(None, description="Filtrer par statut"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(EcritureComptable).order_by(EcritureComptable.date_ecriture.desc())
    
    # Filtres
    if type_operation:
        try:
            from ...models.ecriture_comptable import TypeOperationEnum
            query = query.filter(EcritureComptable.type_operation == TypeOperationEnum(type_operation))
        except ValueError:
            pass
    
    if date_debut:
        try:
            date_obj = datetime.strptime(date_debut, "%Y-%m-%d")
            query = query.filter(EcritureComptable.date_ecriture >= date_obj)
        except ValueError:
            pass
    
    if date_fin:
        try:
            date_obj = datetime.strptime(date_fin, "%Y-%m-%d")
            query = query.filter(EcritureComptable.date_ecriture <= date_obj)
        except ValueError:
            pass
    
    if statut:
        try:
            from ...models.ecriture_comptable import StatutEcriture
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
    type_operation: Optional[str] = Query(None, description="Filtrer par type d'opération"),
    date_debut: Optional[str] = Query(None, description="Date de début (YYYY-MM-DD)"),
    date_fin: Optional[str] = Query(None, description="Date de fin (YYYY-MM-DD)"),
    statut: Optional[str] = Query(None, description="Filtrer par statut"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte les écritures en CSV."""
    if not check_ecriture_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    # Même logique de filtrage que get_all_ecritures
    query = db.query(EcritureComptable).order_by(EcritureComptable.date_ecriture.desc())
    
    if type_operation:
        try:
            from ...models.ecriture_comptable import TypeOperationEnum
            query = query.filter(EcritureComptable.type_operation == TypeOperationEnum(type_operation))
        except ValueError:
            pass
    
    if date_debut:
        try:
            date_obj = datetime.strptime(date_debut, "%Y-%m-%d")
            query = query.filter(EcritureComptable.date_ecriture >= date_obj)
        except ValueError:
            pass
    
    if date_fin:
        try:
            date_obj = datetime.strptime(date_fin, "%Y-%m-%d")
            query = query.filter(EcritureComptable.date_ecriture <= date_obj)
        except ValueError:
            pass
    
    if statut:
        try:
            from ...models.ecriture_comptable import StatutEcriture
            query = query.filter(EcritureComptable.statut == StatutEcriture(statut))
        except ValueError:
            pass
    
    ecritures = query.all()
    
    # Génération du CSV
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
            e.compte_debit,
            e.compte_credit,
            f"{e.montant:.2f}",
            e.libelle or "",
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
    
    if ecriture.statut not in [StatutEcriture.BROUILLON, StatutEcriture.EN_ATTENTE]:
        raise HTTPException(status_code=400, detail="Impossible de modifier une écriture validée")
    
    if "montant" in data:
        ecriture.montant = float(data["montant"])
    if "commentaire" in data:
        ecriture.commentaire = data["commentaire"]
    
    ecriture.date_modification = None
    ecriture.modifie_par = current_user.id
    
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

    try:
        service = ComptabiliteService(db, cree_par_id=current_user.id)
        result = service.reprendre_depreciation(
            bien_id=data["bien_id"],
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
        from datetime import datetime, timedelta
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        debut_jour = date_obj
        fin_jour = date_obj + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide. Utilisez YYYY-MM-DD")
    
    ecritures = db.query(EcritureComptable).filter(
        EcritureComptable.type_operation == "AMORTISSEMENT",
        EcritureComptable.date_ecriture >= debut_jour,
        EcritureComptable.date_ecriture < fin_jour,
        EcritureComptable.statut == "VALIDEE"
    ).order_by(EcritureComptable.numero_piece).all()
    
    result = []
    for e in ecritures:
        bien = db.query(Bien).filter(Bien.id_bien == e.id_bien).first()
        result.append({
            "numero_piece": e.numero_piece,
            "date": e.date_ecriture.strftime("%Y-%m-%d") if e.date_ecriture else None,
            "compte_debit": e.compte_debit,
            "compte_credit": e.compte_credit,
            "montant": e.montant,
            "libelle": e.libelle,
            "bien_reference": _get_bien_designation(bien) if bien else None
        })
    
    return result