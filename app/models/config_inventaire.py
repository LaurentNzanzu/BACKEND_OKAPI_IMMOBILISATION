from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from ..core.database import Base


class ConfigInventaire(Base):
    __tablename__ = "config_inventaire"

    id = Column(Integer, primary_key=True, index=True)
    regle = Column(String(255), nullable=False, default="INV-{YEAR}-{SEQ}")
    longueur_sequence = Column(Integer, nullable=False, default=4)
    reset_period = Column(String(20), nullable=False, default="annuel")  # annuel, mensuel, jamais
    dernier_numero = Column(Integer, nullable=False, default=0)
    date_mise_a_jour = Column(DateTime, server_default=func.now(), onupdate=func.now())