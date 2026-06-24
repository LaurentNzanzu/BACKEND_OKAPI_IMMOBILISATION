# backend/app/api/endpoints/etats.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.etats_service import EtatsService
from ...utils.etats_pdf_generator import generate_fiche_bien_pdf

router = APIRouter(prefix="/etats", tags=["États imprimables"])

# backend/app/api/endpoints/etats.py
# Modifier la fonction check_etat_permission

def check_etat_permission(user: Utilisateur, etat_type: str) -> bool:
    """Vérifie les permissions pour consulter un état"""
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role == "ADMIN":
        return True
    # Tous les rôles authentifiés peuvent voir les états de base
    if etat_type in ["fiche_bien"]:
        return True
    if etat_type in ["etat_besoin"]:
        return True
    # Rapports d'amortissement : ADMIN, DG, COMPTABLE
    if etat_type in ["fiche_amortissement"]:
        return role in ["DG", "COMPTABLE"]
    return False

@router.get("/fiche-bien/{bien_id}")
async def export_fiche_bien(
    bien_id: int,
    format: str = Query("pdf", regex="^(pdf|json)$"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte la fiche détaillée d'un bien au format PDF ou JSON (aperçu)."""
    if not check_etat_permission(current_user, "fiche_bien"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour exporter cette fiche"
        )
    
    service = EtatsService(db)
    data = service.get_fiche_bien_data(bien_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bien {bien_id} non trouvé"
        )

    if format == "json":
        return JSONResponse(content=data)
    
    # Génération du PDF
    pdf_bytes = generate_fiche_bien_pdf(data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fiche_bien_{bien_id}_{timestamp}.pdf"
    
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/etat-besoins/{besoin_id}")
async def export_etat_besoin(
    besoin_id: int,
    format: str = Query("pdf", regex="^(pdf|json)$"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte l'état de sortie d'une demande de besoin (PDF ou JSON pour aperçu)."""
    if not check_etat_permission(current_user, "etat_besoin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour exporter cet état"
        )

    service = EtatsService(db)
    data = service.get_etat_besoin_data(besoin_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Besoin {besoin_id} non trouvé"
        )

    if format == "json":
        return JSONResponse(content=data)

    from ...utils.etats_pdf_generator import generate_etat_besoin_pdf
    pdf_bytes = generate_etat_besoin_pdf(data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    numero = data["besoin"].get("numero_demande", besoin_id)
    filename = f"etat_sortie_besoin_{numero}_{timestamp}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/fiche-amortissement/{bien_id}")
async def export_fiche_amortissement(
    bien_id: int,
    format: str = Query("pdf", regex="^(pdf|json)$"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte la fiche d'amortissement détaillée d'un bien (PDF ou JSON)."""
    if not check_etat_permission(current_user, "fiche_amortissement"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour exporter cette fiche d'amortissement"
        )
    
    service = EtatsService(db)
    data = service.get_fiche_amortissement_data(bien_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bien {bien_id} non trouvé"
        )

    if format == "json":
        return JSONResponse(content=data)
    
    # Génération du PDF
    from ...utils.etats_pdf_generator import generate_fiche_amortissement_pdf
    pdf_bytes = generate_fiche_amortissement_pdf(data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fiche_amortissement_{bien_id}_{timestamp}.pdf"
    
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )