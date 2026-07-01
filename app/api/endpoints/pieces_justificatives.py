# backend/app/api/endpoints/pieces_justificatives.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.piece_justificative import PieceJustificativeResponse
from ...services.piece_justificative_service import PieceJustificativeService

router = APIRouter(prefix="/pieces-justificatives", tags=["Pièces Justificatives"])


@router.get("/{id_piece}/download")
def telecharger_piece(
    id_piece: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = PieceJustificativeService(db)
    pdf_url = service.get_pdf_url(id_piece)
    if not pdf_url:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    
    filepath = os.path.join(os.getcwd(), pdf_url.lstrip("/"))
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Fichier inexistant sur le disque")
    
    return FileResponse(filepath, media_type="application/pdf", filename=os.path.basename(filepath))


@router.post("/{id_piece}/sign-caissier", response_model=PieceJustificativeResponse)
def signature_caissier(
    id_piece: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PieceJustificativeService(db)
    try:
        return service.signer_caissier(id_piece)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{id_piece}/sign-dg", response_model=PieceJustificativeResponse)
def signature_dg(
    id_piece: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = PieceJustificativeService(db)
    try:
        return service.signer_dg(id_piece)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
