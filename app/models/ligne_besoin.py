from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from ..core.database import Base

class LigneBesoin(Base):
    __tablename__ = "lignes_besoin"

    id_ligne = Column(Integer, primary_key=True, index=True)
    id_besoin = Column(Integer, ForeignKey("besoins.id_besoin", ondelete="CASCADE"), nullable=False)
    id_piece = Column(Integer, ForeignKey("pieces_rechange.id_piece"), nullable=False)
    quantite = Column(Integer, nullable=False, default=1)
    prix_unitaire = Column(Float, nullable=False)
    prix_total = Column(Float, nullable=False)

    # Relations
    besoin = relationship("Besoin", back_populates="lignes")
    piece = relationship("PieceRechange", back_populates="lignes_besoin")

    def calculer_prix_total(self):
        """Calcule le prix total de la ligne"""
        self.prix_total = self.quantite * self.prix_unitaire
        return self.prix_total