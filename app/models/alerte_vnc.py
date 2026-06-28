# backend/app/models/alerte_vnc.py
from sqlalchemy import Column, Integer, Float, DateTime, Boolean, String, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class StatutAlerteVNC(enum.Enum):
    EN_ATTENTE = "EN_ATTENTE"
    EN_COURS = "EN_COURS"
    TRAITEE = "TRAITEE"
    ANNULEE = "ANNULEE"

class AlerteVNC(Base):
    __tablename__ = "alertes_vnc"
    
    id = Column(Integer, primary_key=True, index=True)
    bien_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False, index=True)
    
    # Seuil atteint (20% ou 5%)
    seuil_atteint = Column(String(10), nullable=False)  # '20%' ou '5%'
    ratio_vnc = Column(Float, nullable=False)  # Le ratio calculé
    valeur_vnc = Column(Float, nullable=False)  # La VNC au moment de l'alerte
    valeur_origine = Column(Float, nullable=False)  # Valeur d'origine
    
    date_alerte = Column(DateTime, default=datetime.utcnow)
    statut = Column(Enum(StatutAlerteVNC), default=StatutAlerteVNC.EN_ATTENTE)
    date_traitement = Column(DateTime, nullable=True)
    
    # Si une maintenance a été générée
    maintenance_id = Column(Integer, ForeignKey("maintenances.id_maintenance", ondelete="SET NULL"), nullable=True)
    
    # Description et actions
    description = Column(Text, nullable=True)
    action_recommandee = Column(Text, nullable=True)
    action_effectuee = Column(Text, nullable=True)
    
    # Utilisateur ayant traité l'alerte
    traite_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    
    # Relations
    bien = relationship("Bien", back_populates="alertes_vnc")
    maintenance = relationship("Maintenance", foreign_keys=[maintenance_id])
    traite_par = relationship("Utilisateur", foreign_keys=[traite_par_id])
    
    def __repr__(self):
        return f"<AlerteVNC {self.seuil_atteint} - Bien {self.bien_id}>"