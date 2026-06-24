from sqlalchemy import Column, Integer, ForeignKey, Date, String, Numeric, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class Cession(Base):
    __tablename__ = "cessions"

    id_cession = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    date_cession = Column(Date, nullable=False)
    prix_vente = Column(Numeric(15, 2), nullable=False)
    acheteur = Column(String(255))
    mode_reglement = Column(String(50))
    type_cession = Column(String(20), nullable=False)
    resultat = Column(Numeric(15, 2))
    created_at = Column(DateTime, server_default=func.now())

    bien = relationship("Bien", backref="cessions")
