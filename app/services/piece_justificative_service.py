# backend/app/services/piece_justificative_service.py
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from ..models.piece_justificative import PieceJustificative
from ..models.mouvement_caisse import MouvementCaisse
from ..models.caisse import Caisse
from ..schemas.piece_justificative import PieceJustificativeCreate

logger = logging.getLogger(__name__)


class PieceJustificativeService:
    def __init__(self, db: Session):
        self.db = db

    # ═══ 5.22 — Helpers multi-tenant ═══
    def _get_organisation_id_mouvement(self, id_mouvement: Optional[int]) -> Optional[int]:
        """
        Récupère l'organisation_id via MouvementCaisse → Caisse.
        (Après 5.22, MouvementCaisse a sa propre colonne organisation_id
         mais on garde le fallback via Caisse pour les données historiques.)
        """
        if not id_mouvement:
            return None

        mouvement = self.db.query(MouvementCaisse).filter(
            MouvementCaisse.id_mouvement == id_mouvement
        ).first()
        if not mouvement:
            return None

        # 1. Colonne directe (disponible après 5.22)
        org = getattr(mouvement, "organisation_id", None)
        if org is not None:
            return org

        # 2. Fallback via la caisse
        id_caisse = getattr(mouvement, "id_caisse", None)
        if id_caisse:
            caisse = self.db.query(Caisse).filter(Caisse.id_caisse == id_caisse).first()
            return getattr(caisse, "organisation_id", None) if caisse else None

        return None

    def _check_acces_piece(self, piece: PieceJustificative, organisation_id: Optional[int]) -> None:
        """Vérifie que la pièce appartient à l'organisation (None = admin plateforme)."""
        if organisation_id is None or not piece:
            return
        org = getattr(piece, "organisation_id", None)
        if org is None:
            org = self._get_organisation_id_mouvement(piece.id_mouvement)
        if org is None:
            raise ValueError(
                f"Accès refusé : pièce justificative #{piece.id_piece} sans organisation."
            )
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : pièce justificative #{piece.id_piece} appartient à une autre organisation."
            )
    # ═══ FIN 5.22 ═══

    # ═══ MODIF 5.22 — Injection organisation_id ═══
    def creer_piece_justificative(self, data: PieceJustificativeCreate, organisation_id: Optional[int] = None) -> PieceJustificative:
        org_id = organisation_id if organisation_id is not None else self._get_organisation_id_mouvement(data.id_mouvement)

        piece = PieceJustificative(
            id_mouvement=data.id_mouvement,
            type_document=data.type_document,
            numero_document=data.numero_document,
            url_fichier=data.url_fichier,
            organisation_id=org_id,   # ═══ 5.22 ═══
        )
        self.db.add(piece)
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def signer_caissier(self, id_piece: int, organisation_id: Optional[int] = None) -> PieceJustificative:
        piece = self.db.query(PieceJustificative).filter(PieceJustificative.id_piece == id_piece).first()
        if not piece:
            raise ValueError("Pièce justificative non trouvée")
        self._check_acces_piece(piece, organisation_id)

        piece.signature_caissier = True
        piece.date_signature_caissier = datetime.utcnow()
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def signer_dg(self, id_piece: int, organisation_id: Optional[int] = None) -> PieceJustificative:
        piece = self.db.query(PieceJustificative).filter(PieceJustificative.id_piece == id_piece).first()
        if not piece:
            raise ValueError("Pièce justificative non trouvée")
        self._check_acces_piece(piece, organisation_id)

        piece.signature_dg = True
        piece.date_signature_dg = datetime.utcnow()
        self.db.commit()
        self.db.refresh(piece)
        return piece

    def get_piece_by_mouvement(self, id_mouvement: int, organisation_id: Optional[int] = None) -> Optional[PieceJustificative]:
        query = self.db.query(PieceJustificative).filter(PieceJustificative.id_mouvement == id_mouvement)
        if organisation_id is not None:
            query = query.filter(PieceJustificative.organisation_id == organisation_id)
        return query.first()

    def get_pdf_url(self, id_piece: int, organisation_id: Optional[int] = None) -> Optional[str]:
        query = self.db.query(PieceJustificative).filter(PieceJustificative.id_piece == id_piece)
        if organisation_id is not None:
            query = query.filter(PieceJustificative.organisation_id == organisation_id)
        piece = query.first()
        return piece.url_fichier if piece else None
    # ═══ FIN MODIF 5.22 ═══