# backend/app/models/historique_statut_ecriture.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class HistoriqueStatutEcriture(Base):
    __tablename__ = "historique_statuts_ecritures"

    id_historique = Column(Integer, primary_key=True, index=True)
    id_ecriture = Column(Integer, ForeignKey("ecritures_comptables.id_ecriture", ondelete="CASCADE"), nullable=False)
    ancien_statut = Column(String(30), nullable=False)
    nouveau_statut = Column(String(30), nullable=False)
    date_changement = Column(DateTime, default=datetime.utcnow, nullable=False)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    commentaire = Column(Text, nullable=True)

    ecriture = relationship("EcritureComptable")
    utilisateur = relationship("Utilisateur")
