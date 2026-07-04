# backend/app/models/piece_justificative.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class PieceJustificative(Base):
    __tablename__ = "pieces_justificatives"

    id_piece = Column(Integer, primary_key=True, index=True)
    id_mouvement = Column(Integer, ForeignKey("mouvements_caisse.id_mouvement", ondelete="CASCADE"), nullable=False)
    type_document = Column(String(10), nullable=False)  # 'BEC' ou 'BSC'
    numero_document = Column(String(50), nullable=False)
    url_fichier = Column(String(255), nullable=False)
    signature_caissier = Column(Boolean, default=False, nullable=False)
    signature_dg = Column(Boolean, default=False, nullable=False)
    date_signature_caissier = Column(DateTime, nullable=True)
    date_signature_dg = Column(DateTime, nullable=True)

    # Satisfaire les colonnes NOT NULL existantes de la table d'origine
    type_piece = Column(String(20), nullable=False, default="FONDS")
    titre = Column(String(100), nullable=False, default="Pièce justificative de caisse")
    fichier_nom = Column(String(100), nullable=False, default="piece.pdf")
    fichier_url = Column(String(255), nullable=False, default="/")

    mouvement = relationship("MouvementCaisse", back_populates="piece_justificative")

    def __init__(self, **kwargs):
        import os
        super().__init__(**kwargs)
        if "type_document" in kwargs:
            self.type_piece = "FONDS" if kwargs["type_document"] == "BEC" else "DECAISSEMENT"
        if "url_fichier" in kwargs:
            self.fichier_url = kwargs["url_fichier"]
            try:
                self.fichier_nom = os.path.basename(kwargs["url_fichier"])
            except Exception:
                self.fichier_nom = "piece.pdf"
        if "numero_document" in kwargs:
            self.titre = f"Bon {kwargs['numero_document']}"
