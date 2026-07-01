# backend/app/services/piece_justificative_service.py
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from ..models.piece_justificative import PieceJustificative
from ..schemas.piece_justificative import PieceJustificativeCreate


class PieceJustificativeService:
    def __init__(self, db: Session):
        self.db = db

    def creer_piece_justificative(self, data: PieceJustificativeCreate) -> PieceJustificative:
        piece = PieceJustificative(
            id_mouvement=data.id_mouvement,
            type_document=data.type_document,
            numero_document=data.numero_document,
            url_fichier=data.url_fichier
        )
        self.db.add(piece)
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def signer_caissier(self, id_piece: int) -> PieceJustificative:
        piece = self.db.query(PieceJustificative).filter(PieceJustificative.id_piece == id_piece).first()
        if not piece:
            raise ValueError("Pièce justificative non trouvée")
        piece.signature_caissier = True
        piece.date_signature_caissier = datetime.utcnow()
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def signer_dg(self, id_piece: int) -> PieceJustificative:
        piece = self.db.query(PieceJustificative).filter(PieceJustificative.id_piece == id_piece).first()
        if not piece:
            raise ValueError("Pièce justificative non trouvée")
        piece.signature_dg = True
        piece.date_signature_dg = datetime.utcnow()
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def get_piece_by_mouvement(self, id_mouvement: int) -> Optional[PieceJustificative]:
        return self.db.query(PieceJustificative).filter(PieceJustificative.id_mouvement == id_mouvement).first()

    def get_pdf_url(self, id_piece: int) -> Optional[str]:
        piece = self.db.query(PieceJustificative).filter(PieceJustificative.id_piece == id_piece).first()
        return piece.url_fichier if piece else None
