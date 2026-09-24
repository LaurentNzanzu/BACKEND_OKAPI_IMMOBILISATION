from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Optional
import logging

from ..models.besoin import Besoin
from ..models.ligne_besoin import LigneBesoin
from ..models.piece_rechange import PieceRechange
from ..models.bien import Bien
from ..models.panne import Panne

logger = logging.getLogger(__name__)


class StockService:
    def __init__(self, db: Session):
        self.db = db

    # ═══ 5.22 — Helpers multi-tenant ═══
    def _get_organisation_id_besoin(self, id_besoin: Optional[int]) -> Optional[int]:
        if not id_besoin:
            return None
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            return None
        org = getattr(besoin, "organisation_id", None)
        if org is not None:
            return org
        if besoin.id_panne:
            panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
            if panne and panne.id_bien:
                bien = self.db.query(Bien).filter(Bien.id_bien == panne.id_bien).first()
                return getattr(bien, "organisation_id", None) if bien else None
        return None

    def _check_acces_besoin(self, id_besoin: int, organisation_id: Optional[int]) -> None:
        if organisation_id is None:
            return
        org = self._get_organisation_id_besoin(id_besoin)
        if org is None:
            raise ValueError(f"Accès refusé : besoin #{id_besoin} sans organisation.")
        if org != organisation_id:
            raise ValueError(f"Accès refusé : besoin #{id_besoin} appartient à une autre organisation.")
    # ═══ FIN 5.22 ═══

    # ═══ MODIF 5.22 — Vérif accès ═══
    def verifier_disponibilite(self, besoin_id: int, organisation_id: Optional[int] = None) -> Dict[int, dict]:
        self._check_acces_besoin(besoin_id, organisation_id)
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

    def verifier_stock_suffisant_pour_besoin(self, besoin_id: int, organisation_id: Optional[int] = None) -> bool:
        disponibilite = self.verifier_disponibilite(besoin_id, organisation_id=organisation_id)
        return all(info["suffisant"] for info in disponibilite.values())

    def evaluer_stock_besoin(self, besoin_id: int, organisation_id: Optional[int] = None) -> str:
        disponibilite = self.verifier_disponibilite(besoin_id, organisation_id=organisation_id)
        if not disponibilite:
            return "TOUT_DISPONIBLE"

        has_zero = any(info["disponible"] == 0 for info in disponibilite.values())
        has_insufficient = any(not info["suffisant"] for info in disponibilite.values())

        if has_zero:
            return "STOCK_NUL"
        if has_insufficient:
            return "STOCK_INSUFFISANT"
        return "TOUT_DISPONIBLE"

    def get_pieces_manquantes(self, besoin_id: int, organisation_id: Optional[int] = None) -> List[dict]:
        disponibilite = self.verifier_disponibilite(besoin_id, organisation_id=organisation_id)
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

    def get_pieces_stock_faible(self, seuil_relatif: float = 0.2, organisation_id: Optional[int] = None) -> List[PieceRechange]:
        query = self.db.query(PieceRechange).filter(PieceRechange.est_active == True)
        if organisation_id is not None:
            query = query.filter(PieceRechange.organisation_id == organisation_id)
        pieces = query.all()
        result = []
        for piece in pieces:
            seuil = max(1, int(piece.stock_minimum * seuil_relatif))
            if piece.stock_actuel < piece.stock_minimum or piece.stock_actuel < seuil:
                result.append(piece)
        return result
