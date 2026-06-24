from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base

class PlanComptable(Base):
    __tablename__ = "plan_comptable"
    
    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(10), unique=True, nullable=False, index=True)
    libelle = Column(String(255), nullable=False)
    classe = Column(String(1), nullable=False)
    type = Column(String(20), nullable=False)  # actif, passif, charge, produit
    est_actif = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_plan_comptable_classe', 'classe'),
        Index('ix_plan_comptable_type', 'type'),
    )
    
    def __repr__(self):
        return f"<PlanComptable(numero='{self.numero}', libelle='{self.libelle}')>"