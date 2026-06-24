from sqlalchemy.orm import Session, joinedload
from typing import List, Dict
from ..models.besoin import Besoin
from ..models.ligne_besoin import LigneBesoin
from ..models.piece_rechange import PieceRechange


class StockService:
    def __init__(self, db: Session):
        self.db = db

    def verifier_disponibilite(self, besoin_id: int) -> Dict[int, dict]:
        besoin = (
            self.db.query(Besoin)
            .options(joinedload(Besoin.lignes).joinedload(LigneBesoin.piece))
            .filter(Besoin.id_besoin == besoin_id)
            .first()
        )
        if not besoin:
            raise ValueError("Besoin non trouvé")

        result = {}
        for ligne in besoin.lignes:
            piece = ligne.piece
            stock = piece.stock_actuel if piece else 0
            result[ligne.id_piece] = {
                "disponible": stock,
                "demande": ligne.quantite,
                "suffisant": stock >= ligne.quantite,
                "designation": piece.designation if piece else None,
            }
        return result

    def verifier_stock_suffisant_pour_besoin(self, besoin_id: int) -> bool:
        disponibilite = self.verifier_disponibilite(besoin_id)
        return all(info["suffisant"] for info in disponibilite.values())

    def evaluer_stock_besoin(self, besoin_id: int) -> str:
        disponibilite = self.verifier_disponibilite(besoin_id)
        if not disponibilite:
            return "TOUT_DISPONIBLE"

        has_zero = any(info["disponible"] == 0 for info in disponibilite.values())
        has_insufficient = any(not info["suffisant"] for info in disponibilite.values())

        if has_zero:
            return "STOCK_NUL"
        if has_insufficient:
            return "STOCK_INSUFFISANT"
        return "TOUT_DISPONIBLE"

    def get_pieces_manquantes(self, besoin_id: int) -> List[dict]:
        disponibilite = self.verifier_disponibilite(besoin_id)
        manquantes = []
        for id_piece, info in disponibilite.items():
            if not info["suffisant"]:
                manquantes.append({
                    "id_piece": id_piece,
                    "designation": info["designation"],
                    "quantite_demandee": info["demande"],
                    "stock_disponible": info["disponible"],
                    "quantite_manquante": info["demande"] - info["disponible"],
                })
        return manquantes

    def get_pieces_stock_faible(self, seuil_relatif: float = 0.2) -> List[PieceRechange]:
        pieces = self.db.query(PieceRechange).filter(PieceRechange.est_active == True).all()
        result = []
        for piece in pieces:
            seuil = max(1, int(piece.stock_minimum * seuil_relatif))
            if piece.stock_actuel < piece.stock_minimum or piece.stock_actuel < seuil:
                result.append(piece)
        return result
