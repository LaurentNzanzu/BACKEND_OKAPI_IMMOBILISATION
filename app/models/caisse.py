# backend/app/models/caisse.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Numeric
from datetime import datetime
from ..core.database import Base


class Caisse(Base):
    __tablename__ = "caisses"

    id_caisse = Column(Integer, primary_key=True, index=True)
    solde_physique = Column(Float, default=0.0, nullable=False)
    solde_theorique = Column(Float, default=0.0, nullable=False)
    devise = Column(String(10), default="USD", nullable=False)
    dernier_rapprochement = Column(DateTime, nullable=True)
    statut = Column(String(20), default="ACTIF", nullable=False)

    def est_suffisante(self, montant: float) -> bool:
        return self.solde_physique >= montant
