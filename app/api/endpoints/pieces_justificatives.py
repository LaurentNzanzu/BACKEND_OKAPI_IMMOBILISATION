from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.piece_justificative import (
    PieceJustificativeCreate, PieceJustificativeUpdate,
    PieceJustificativeResponse, PieceJustificativeValidation,
    PieceJustificativeSignature
)
from ...services.piece_justificative_service import PieceJustificativeService

router = APIRouter(prefix="/pieces-justificatives", tags=["Pièces Justificatives"])


def _serialize_piece(piece) -> dict:
    data = PieceJustificativeResponse.model_validate(piece).model_dump()
    if piece.upload_par:
        data["upload_par_nom"] = getattr(piece.upload_par, "nom", str(piece.upload_par_id))
    if piece.valide_par:
        data["valide_par_nom"] = getattr(piece.valide_par, "nom", str(piece.valide_par_id))
    if piece.signe_par:
        data["signe_par_nom"] = getattr(piece.signe_par, "nom", str(piece.signe_par_id))
    return data


@router.post("", response_model=PieceJustificativeResponse, status_code=status.HTTP_201_CREATED)
async def create_piece(
    data: PieceJustificativeCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Crée une nouvelle pièce justificative."""
    service = PieceJustificativeService(db)
    piece = service.create(data, current_user.id)
    return _serialize_piece(piece)


@router.get("/transaction/{transaction_type}/{transaction_id}", response_model=List[PieceJustificativeResponse])
async def get_pieces_by_transaction(
    transaction_type: str,
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les pièces liées à une transaction."""
    service = PieceJustificativeService(db)
    try:
        pieces = service.get_by_transaction(transaction_type, transaction_id)
        return [_serialize_piece(p) for p in pieces]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{piece_id}", response_model=PieceJustificativeResponse)
async def get_piece(
    piece_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère une pièce justificative."""
    from ...models.piece_justificative import PieceJustificative
    piece = db.query(PieceJustificative).filter(
        PieceJustificative.id_piece == piece_id
    ).first()
    
    if not piece:
        raise HTTPException(status_code=404, detail="Pièce non trouvée")
    
    return _serialize_piece(piece)


@router.post("/{piece_id}/valider", response_model=PieceJustificativeResponse)
async def valider_piece(
    piece_id: int,
    data: PieceJustificativeValidation,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Valide ou rejette une pièce justificative."""
    service = PieceJustificativeService(db)
    try:
        if data.decision == "VALIDER":
            piece = service.valider(piece_id, current_user.id)
        else:
            if not data.motif:
                raise HTTPException(status_code=400, detail="Le motif de rejet est obligatoire")
            piece = service.rejeter(piece_id, current_user.id, data.motif)
        
        return _serialize_piece(piece)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{piece_id}/signer", response_model=PieceJustificativeResponse)
async def signer_piece(
    piece_id: int,
    data: PieceJustificativeSignature,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Signe électroniquement une pièce justificative."""
    service = PieceJustificativeService(db)
    try:
        piece = service.signer(piece_id, current_user.id, data.signature)
        return _serialize_piece(piece)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
