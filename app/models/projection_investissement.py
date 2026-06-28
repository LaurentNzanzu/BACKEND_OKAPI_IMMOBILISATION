# backend/app/models/projection_investissement.py
from sqlalchemy import Column, Integer, Float, DateTime, String, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class StatutProjection(enum.Enum):
    ESTIMEE = "ESTIMEE"
    CONFIRMEE = "CONFIRMEE"
    REALISEE = "REALISEE"
    ANNULEE = "ANNULEE"


class ProjectionInvestissement(Base):
    __tablename__ = "projections_investissement"
    
    id = Column(Integer, primary_key=True, index=True)
    bien_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False, index=True)
    
    # Année de projection (N+1, N+2, ... N+5)
    annee_projection = Column(Integer, nullable=False)  # 2027, 2028, ...
    
    # Date estimée de fin de vie
    date_fin_vie_estimee = Column(DateTime, nullable=True)
    
    # Critères ayant déclenché la projection
    critere_fin_amortissement = Column(Boolean, default=False)  # VNC = 0
    critere_score_fiabilite = Column(Boolean, default=False)  # SF < 30%
    critere_obligation_legale = Column(Boolean, default=False)
    critere_remplacement_cyclique = Column(Boolean, default=False)
    
    # Coût de remplacement estimé
    cout_remplacement_estime = Column(Float, nullable=False, default=0.0)
    
    # Analyse
    score_fiabilite_projete = Column(Float, nullable=True)
    vnc_projetee = Column(Float, nullable=True)
    taux_obsolescence = Column(Float, nullable=True)  # Taux d'obsolescence estimé
    
    # Statut - ✅ Correction ici
    statut = Column(ENUM(StatutProjection, name='statut_projection'), default=StatutProjection.ESTIMEE)
    
    # Métadonnées
    date_calcul = Column(DateTime, default=datetime.utcnow)
    commentaire = Column(Text, nullable=True)
    
    # Utilisateur ayant validé la projection
    valide_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    date_validation = Column(DateTime, nullable=True)
    
    # Relations
    bien = relationship("Bien", back_populates="projections")
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id])
    
    def __repr__(self):
        return f"<ProjectionInvestissement {self.annee_projection} - Bien {self.bien_id}>"