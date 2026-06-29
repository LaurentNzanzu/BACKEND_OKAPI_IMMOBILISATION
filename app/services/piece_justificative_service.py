from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import logging

from ..models.piece_justificative import PieceJustificative, TypePieceJustificative, StatutPieceJustificative
from ..schemas.piece_justificative import PieceJustificativeCreate, PieceJustificativeUpdate
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class PieceJustificativeService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
    
    def create(self, data: PieceJustificativeCreate, utilisateur_id: int) -> PieceJustificative:
        """Crée une nouvelle pièce justificative."""
        piece = PieceJustificative(
            type_piece=data.type_piece,
            titre=data.titre,
            description=data.description,
            numero_reference=data.numero_reference,
            date_document=data.date_document,
            fichier_nom=data.fichier_nom,
            fichier_url=data.fichier_url,
            fichier_taille=data.fichier_taille,
            fichier_type=data.fichier_type,
            id_bien=data.id_bien,
            id_besoin=data.id_besoin,
            id_amortissement=data.id_amortissement,
            id_cession=data.id_cession,
            id_maintenance=data.id_maintenance,
            id_ecriture=data.id_ecriture,
            upload_par_id=utilisateur_id,
            statut=StatutPieceJustificative.SOUMIS
        )
        
        self.db.add(piece)
        self.db.commit()
        self.db.refresh(piece)
        
        try:
            self.audit_service.log_action(
                user_id=utilisateur_id,
                table_name="pieces_justificatives",
                record_id=piece.id_piece,
                action="CREATE",
                nouvelles_valeurs={
                    "type": piece.type_piece.value if hasattr(piece.type_piece, 'value') else str(piece.type_piece),
                    "titre": piece.titre,
                    "reference": piece.numero_reference
                }
            )
        except Exception as e:
            logger.warning(f"Erreur audit log piece: {e}")
        
        return piece
    
    def valider(self, piece_id: int, utilisateur_id: int) -> PieceJustificative:
        """Valide une pièce justificative."""
        piece = self.db.query(PieceJustificative).filter(
            PieceJustificative.id_piece == piece_id
        ).first()
        
        if not piece:
            raise ValueError("Pièce non trouvée")
        
        piece.valider(utilisateur_id)
        self.db.commit()
        self.db.refresh(piece)
        return piece
    
    def rejeter(self, piece_id: int, utilisateur_id: int, motif: str) -> PieceJustificative:
        """Rejette une pièce justificative."""
        piece = self.db.query(PieceJustificative).filter(
            PieceJustificative.id_piece == piece_id
        ).first()
        
        if not piece:
            raise ValueError("Pièce non trouvée")
        
        piece.rejeter(utilisateur_id, motif)
        self.db.commit()
        self.db.refresh(piece)
        return piece
    
    def signer(self, piece_id: int, utilisateur_id: int, signature: str) -> PieceJustificative:
        """Signe électroniquement une pièce justificative."""
        piece = self.db.query(PieceJustificative).filter(
            PieceJustificative.id_piece == piece_id
        ).first()
        
        if not piece:
            raise ValueError("Pièce non trouvée")
        
        piece.signer(utilisateur_id, signature)
        self.db.commit()
        self.db.refresh(piece)
        return piece
    
    def get_by_transaction(self, transaction_type: str, transaction_id: int) -> List[PieceJustificative]:
        """Récupère les pièces liées à une transaction."""
        field_map = {
            "bien": "id_bien",
            "besoin": "id_besoin",
            "amortissement": "id_amortissement",
            "cession": "id_cession",
            "maintenance": "id_maintenance",
            "ecriture": "id_ecriture"
        }
        
        field = field_map.get(transaction_type.lower())
        if not field:
            raise ValueError(f"Type de transaction invalide: {transaction_type}")
        
        return self.db.query(PieceJustificative).filter(
            getattr(PieceJustificative, field) == transaction_id
        ).all()
