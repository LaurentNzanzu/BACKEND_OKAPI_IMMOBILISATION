# backend/app/services/piece_service.py
from sqlalchemy.orm import Session
from typing import Optional, List
import re
from datetime import datetime
from ..models.piece_rechange import PieceRechange, TypeCompatible
from ..schemas.piece_rechange import PieceRechangeCreate, PieceRechangeUpdate
from ..utils.search import ilike_pattern

class PieceService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_serie_number(self) -> str:
        """
        Génère un numéro de série unique au format AAAAMMJJNN
        - AAAA: année sur 4 chiffres
        - MM: mois sur 2 chiffres
        - JJ: jour sur 2 chiffres
        - NN: numéro séquentiel sur 2 chiffres (01, 02, ...)
        Exemple: 2026060901 pour le 09/06/2026, première pièce du jour
        """
        now = datetime.now()
        date_prefix = now.strftime("%Y%m%d")  # AAAAMMJJ
        
        # Récupérer toutes les pièces créées aujourd'hui
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
        today_pieces = self.db.query(PieceRechange).filter(
            PieceRechange.date_creation >= today_start
        ).count()
        
        # Calculer le numéro séquentiel (commence à 1)
        sequential_num = today_pieces + 1
        
        # Formater sur 2 chiffres (01, 02, ..., 99)
        return f"{date_prefix}{str(sequential_num).zfill(2)}"

    def create_piece(self, data: PieceRechangeCreate) -> PieceRechange:
        piece_data = data.model_dump()
        
        # Si l'utilisateur n'a pas fourni de numéro de série ou si c'est vide
        if not piece_data.get('numero_serie') or piece_data.get('numero_serie').strip() == '':
            piece_data['numero_serie'] = self._generate_serie_number()
        else:
            # Vérifier que le numéro saisi est unique
            existing = self.get_piece_by_serie(piece_data['numero_serie'])
            if existing:
                raise ValueError(f"Le numéro de série {piece_data['numero_serie']} existe déjà")
        
        piece = PieceRechange(**piece_data)
        self.db.add(piece)
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def get_piece(self, id_piece: int) -> Optional[PieceRechange]:
        return self.db.query(PieceRechange).filter(PieceRechange.id_piece == id_piece).first()

    def get_piece_by_serie(self, numero_serie: str) -> Optional[PieceRechange]:
        return self.db.query(PieceRechange).filter(PieceRechange.numero_serie == numero_serie).first()

    def get_all_pieces(self, skip: int = 0, limit: int = 100, est_active: Optional[bool] = None) -> List[PieceRechange]:
        query = self.db.query(PieceRechange)
        if est_active is not None:
            query = query.filter(PieceRechange.est_active == est_active)
        return query.order_by(PieceRechange.date_creation.desc()).offset(skip).limit(limit).all()

    def update_piece(self, id_piece: int, data: PieceRechangeUpdate) -> Optional[PieceRechange]:
        piece = self.get_piece(id_piece)
        if not piece:
            return None
        update_data = data.model_dump(exclude_unset=True)
        
        # Si on essaie de modifier le numéro de série, vérifier l'unicité
        if 'numero_serie' in update_data and update_data['numero_serie'] != piece.numero_serie:
            existing = self.get_piece_by_serie(update_data['numero_serie'])
            if existing and existing.id_piece != id_piece:
                raise ValueError(f"Le numéro de série {update_data['numero_serie']} existe déjà")
        
        for field, value in update_data.items():
            setattr(piece, field, value)
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def delete_piece(self, id_piece: int) -> bool:
        piece = self.get_piece(id_piece)
        if not piece:
            return False
        piece.est_active = False
        self.db.commit()
        return True

    def get_pieces_stock_insuffisant(self) -> List[PieceRechange]:
        return self.db.query(PieceRechange).filter(
            PieceRechange.est_active == True,
            PieceRechange.stock_actuel < PieceRechange.stock_minimum
        ).all()

    def rechercher_par_numero_serie(self, numero_serie: str) -> Optional[PieceRechange]:
        if not numero_serie:
            return None
        return self.db.query(PieceRechange).filter(
            PieceRechange.numero_serie == numero_serie
        ).first()

    def rechercher_par_designation(self, designation: str) -> Optional[PieceRechange]:
        if not designation:
            return None
        pattern = ilike_pattern(designation)
        if not pattern:
            return None
        return self.db.query(PieceRechange).filter(
            PieceRechange.designation.ilike(pattern)
        ).first()

    def decrement_stock(self, id_piece: int, quantite: int) -> int:
        """Décrémente le stock avec verrouillage pessimiste."""
        piece = (
            self.db.query(PieceRechange)
            .filter(PieceRechange.id_piece == id_piece)
            .with_for_update()
            .first()
        )
        if not piece:
            raise ValueError(f"Pièce {id_piece} non trouvée")
        if piece.stock_actuel < quantite:
            raise ValueError(
                f"Stock insuffisant : disponible {piece.stock_actuel}, demandé {quantite}"
            )
        piece.stock_actuel -= quantite
        return piece.stock_actuel