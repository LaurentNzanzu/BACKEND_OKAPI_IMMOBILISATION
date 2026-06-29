# backend/app/models/centre_cout.py
from sqlalchemy import Column, Integer, String, Boolean
from ..core.database import Base


class CentreCout(Base):
    __tablename__ = "centres_cout"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    nom = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    actif = Column(Boolean, default=True, nullable=False)
