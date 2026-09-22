from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from ..core.database import Base

class TypeCompatible(str, enum.Enum):
    VEHICULE = "VEHICULE"
    ORDINATEUR = "ORDINATEUR"
    MACHINE_PRODUCTION = "MACHINE_PRODUCTION"
    
    @classmethod
    def _missing_(cls, value):
        """Gère automatiquement les valeurs en minuscules ou casse mixte"""
        if isinstance(value, str):
            value_upper = value.upper()
            for member in cls:
                if member.value == value_upper:
                    return member
        return None

class PieceRechange(Base):
    __tablename__ = "pieces_rechange"

    id_piece = Column(Integer, primary_key=True, index=True)

    # ═══ 5.22 — Multi-tenant ═══
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Multi-tenant : ONG propriétaire"
    )
    # ═══ FIN 5.22 ═══

    # ═══ 5.22 — unique=True retiré (remplacé par contrainte composite) ═══
    numero_serie = Column(String(50), nullable=True, index=True)
    # ═══ FIN 5.22 ═══

    designation = Column(String(200), nullable=False)
    prix_achat = Column(Float, nullable=False)
    prix_vente = Column(Float, nullable=True)
    stock_actuel = Column(Integer, default=0)
    stock_minimum = Column(Integer, default=5)
    compatible_avec = Column(Enum(TypeCompatible), nullable=False)   # ✅ préservé nullable=False
    fournisseur = Column(String(200), nullable=True)
    est_active = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)

    # Relations
    organisation = relationship("Organisation")   # ═══ 5.22 ═══
    lignes_besoin = relationship("LigneBesoin", back_populates="piece")
    fournitures = relationship("FourniturePiece", back_populates="piece")

    # ═══ 5.22 — Contrainte UNIQUE scopée par ONG ═══
    __table_args__ = (
        UniqueConstraint('organisation_id', 'numero_serie', name='uq_piece_rechange_org_numero_serie'),
    )
    # ═══ FIN 5.22 ═══

    def est_en_stock_insuffisant(self) -> bool:
        """Vérifie si le stock est en dessous du seuil minimum"""
        return self.stock_actuel < self.stock_minimum
    
    def get_compatible_display(self) -> str:
        """Retourne l'affichage lisible du type de compatibilité"""
        compatibles = {
            TypeCompatible.VEHICULE: "Véhicule",
            TypeCompatible.ORDINATEUR: "Ordinateur",
            TypeCompatible.MACHINE_PRODUCTION: "Machine de production"
        }
        return compatibles.get(self.compatible_avec, self.compatible_avec.value)