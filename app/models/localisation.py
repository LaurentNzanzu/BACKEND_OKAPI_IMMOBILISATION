from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from ..core.database import Base


class Localisation(Base):
    __tablename__ = "localisations"

    id_localisation = Column(Integer, primary_key=True, index=True)
    nom_localisation = Column(String(200), unique=True, nullable=False, index=True)

    biens = relationship("Bien", back_populates="localisation_ref")
