from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    Enum as SQLEnum,
    CheckConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class StatutFourniture(enum.Enum):
    EN_ATTENTE = "EN_ATTENTE"
    FOURNIE = "FOURNIE"
    PARTIELLE = "PARTIELLE"
    REFUSEE = "REFUSEE"
    ANNULEE = "ANNULEE"


class FourniturePiece(Base):
    __tablename__ = "fournitures_pieces"
    __table_args__ = (
        CheckConstraint("quantite_demandee > 0", name="ck_fourniture_quantite_demandee_positive"),
    )

    id_fourniture = Column(Integer, primary_key=True, index=True)
    id_besoin = Column(
        Integer,
        ForeignKey("besoins.id_besoin", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_piece = Column(
        Integer,
        ForeignKey("pieces_rechange.id_piece", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantite_demandee = Column(Integer, nullable=False)
    quantite_fournie = Column(Integer, nullable=True)
    date_fourniture = Column(DateTime, nullable=True, index=True)
    id_magasinier = Column(
        Integer,
        ForeignKey("utilisateurs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    statut = Column(
        SQLEnum(StatutFourniture, name="statut_fourniture"),
        nullable=False,
        default=StatutFourniture.EN_ATTENTE,
    )
    commentaire = Column(Text, nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_modification = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    besoin = relationship("Besoin", back_populates="fournitures")
    piece = relationship("PieceRechange", back_populates="fournitures")
    magasinier = relationship("Utilisateur", back_populates="fournitures_validees")
