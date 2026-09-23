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

    # ═══ MODIF 5.22 — Numéro de série scopé par ONG ═══
    def _generate_serie_number(self, organisation_id: Optional[int] = None) -> str:
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
        query = self.db.query(PieceRechange).filter(
            PieceRechange.date_creation >= today_start
        )
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        today_pieces = query.count()
        
        # Calculer le numéro séquentiel (commence à 1)
        sequential_num = today_pieces + 1
        
        # Formater sur 2 chiffres (01, 02, ..., 99)
        return f"{date_prefix}{str(sequential_num).zfill(2)}"
    # ═══ FIN MODIF 5.22 ═══

    # ═══ MODIF 5.22 — Injection organisation_id ═══
    def create_piece(self, data: PieceRechangeCreate, organisation_id: Optional[int] = None) -> PieceRechange:
        piece_data = data.model_dump()
        
        # Si l'utilisateur n'a pas fourni de numéro de série ou si c'est vide
        if not piece_data.get('numero_serie') or piece_data.get('numero_serie').strip() == '':
            piece_data['numero_serie'] = self._generate_serie_number(organisation_id=organisation_id)
        else:
            # Vérifier que le numéro saisi est unique
            existing = self.get_piece_by_serie(piece_data['numero_serie'], organisation_id=organisation_id)
            if existing:
                raise ValueError(f"Le numéro de série {piece_data['numero_serie']} existe déjà")
        
        # ═══ 5.22 — Injection organisation_id ═══
        if organisation_id is not None:
            piece_data['organisation_id'] = organisation_id
        # ═══ FIN 5.22 ═══
        
        piece = PieceRechange(**piece_data)
        self.db.add(piece)
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def get_piece(self, id_piece: int, organisation_id: Optional[int] = None) -> Optional[PieceRechange]:
        query = self.db.query(PieceRechange).filter(PieceRechange.id_piece == id_piece)
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        return query.first()

    def get_piece_by_serie(self, numero_serie: str, organisation_id: Optional[int] = None) -> Optional[PieceRechange]:
        query = self.db.query(PieceRechange).filter(PieceRechange.numero_serie == numero_serie)
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        return query.first()

    def get_all_pieces(self, skip: int = 0, limit: int = 100, est_active: Optional[bool] = None, organisation_id: Optional[int] = None) -> List[PieceRechange]:
        query = self.db.query(PieceRechange)
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        if est_active is not None:
            query = query.filter(PieceRechange.est_active == est_active)
        return query.order_by(PieceRechange.date_creation.desc()).offset(skip).limit(limit).all()

    def update_piece(self, id_piece: int, data: PieceRechangeUpdate, organisation_id: Optional[int] = None) -> Optional[PieceRechange]:
        piece = self.get_piece(id_piece, organisation_id=organisation_id)
        if not piece:
            return None
        update_data = data.model_dump(exclude_unset=True)
        
        # Si on essaie de modifier le numéro de série, vérifier l'unicité
        if 'numero_serie' in update_data and update_data['numero_serie'] != piece.numero_serie:
            existing = self.get_piece_by_serie(update_data['numero_serie'], organisation_id=organisation_id)
            if existing and existing.id_piece != id_piece:
                raise ValueError(f"Le numéro de série {update_data['numero_serie']} existe déjà")
        
        for field, value in update_data.items():
            setattr(piece, field, value)
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def delete_piece(self, id_piece: int, organisation_id: Optional[int] = None) -> bool:
        piece = self.get_piece(id_piece, organisation_id=organisation_id)
        if not piece:
            return False
        piece.est_active = False
        self.db.commit()
        return True

    def get_pieces_stock_insuffisant(self, organisation_id: Optional[int] = None) -> List[PieceRechange]:
        query = self.db.query(PieceRechange).filter(
            PieceRechange.est_active == True,
            PieceRechange.stock_actuel < PieceRechange.stock_minimum
        )
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        return query.all()

    def rechercher_par_numero_serie(self, numero_serie: str, organisation_id: Optional[int] = None) -> Optional[PieceRechange]:
        if not numero_serie:
            return None
        query = self.db.query(PieceRechange).filter(
            PieceRechange.numero_serie == numero_serie
        )
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        return query.first()

    def rechercher_par_designation(self, designation: str, organisation_id: Optional[int] = None) -> Optional[PieceRechange]:
        if not designation:
            return None
        pattern = ilike_pattern(designation)
        if not pattern:
            return None
        query = self.db.query(PieceRechange).filter(
            PieceRechange.designation.ilike(pattern)
        )
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        return query.first()

    def decrement_stock(self, id_piece: int, quantite: int, organisation_id: Optional[int] = None) -> int:
        """Décrémente le stock avec verrouillage pessimiste."""
        query = self.db.query(PieceRechange).filter(PieceRechange.id_piece == id_piece)
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        piece = query.with_for_update().first()
        if not piece:
            raise ValueError(f"Pièce {id_piece} non trouvée")
        if piece.stock_actuel < quantite:
            raise ValueError(
                f"Stock insuffisant : disponible {piece.stock_actuel}, demandé {quantite}"
            )
        piece.stock_actuel -= quantite
        return piece.stock_actuel
    # ═══ FIN MODIF 5.22 ═══