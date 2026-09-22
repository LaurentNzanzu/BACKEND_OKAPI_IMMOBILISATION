# backend/app/models/ligne_besoin.py
from sqlalchemy import Column, Integer, Float, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from ..core.database import Base

class LigneBesoin(Base):
    __tablename__ = "lignes_besoin"

    id_ligne = Column(Integer, primary_key=True, index=True)

    # ═══ 5.22 — Multi-tenant ═══
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Multi-tenant : ONG propriétaire (héritée du besoin)"
    )
    # ═══ FIN 5.22 ═══

    id_besoin = Column(Integer, ForeignKey("besoins.id_besoin", ondelete="CASCADE"), nullable=False)
    
    id_piece = Column(Integer, ForeignKey("pieces_rechange.id_piece", ondelete="SET NULL"), nullable=True)
    
    quantite = Column(Integer, nullable=False, default=1)
    prix_unitaire = Column(Float, nullable=False, default=0.0)
    prix_total = Column(Float, nullable=False, default=0.0)
    
    est_hors_catalogue = Column(Boolean, default=False, nullable=False)
    designation_hors_catalogue = Column(String(200), nullable=True)

    # Relations
    organisation = relationship("Organisation")   # ═══ 5.22 ═══
    besoin = relationship("Besoin", back_populates="lignes")
    piece = relationship("PieceRechange", foreign_keys=[id_piece], back_populates="lignes_besoin")

    def calculer_prix_total(self):
        """Calcule le prix total de la ligne"""
        self.prix_total = self.quantite * self.prix_unitaire
        return self.prix_total