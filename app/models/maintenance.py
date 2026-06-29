# backend/app/models/maintenance.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class TypeMaintenance(enum.Enum):
    PREVENTIVE = "PREVENTIVE"
    CORRECTIVE = "CORRECTIVE"
    PREDICTIVE = "PREDICTIVE"
    CURATIVE = "CURATIVE"

class TypeOrigineMaintenance(enum.Enum):
    AUTO = "AUTO"  # Généré automatiquement
    MANUEL = "MANUEL"  # Créé manuellement

class StatutMaintenance(enum.Enum):
    PLANIFIEE = "PLANIFIEE"
    EN_COURS = "EN_COURS"
    TERMINEE = "TERMINEE"
    REPORTEE = "REPORTEE"
    ANNULEE = "ANNULEE"

class Maintenance(Base):
    __tablename__ = "maintenances"

    id_maintenance = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    id_panne = Column(Integer, ForeignKey("pannes.id_panne", ondelete="SET NULL"), nullable=True, index=True)
    id_technicien = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    type_maintenance = Column(SQLEnum(TypeMaintenance), nullable=False)
    statut = Column(SQLEnum(StatutMaintenance), default=StatutMaintenance.PLANIFIEE)
    date_planifiee = Column(DateTime, nullable=False)
    date_debut_reelle = Column(DateTime, nullable=True)
    date_fin_reelle = Column(DateTime, nullable=True)
    periodicite_jours = Column(Integer, nullable=True)
    cout = Column(Float, default=0.0)
    description = Column(Text, nullable=False)
    observation = Column(Text, nullable=True)
    pieces_remplacees = Column(Text, nullable=True)
    rapport = Column(Text, nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    
    # === NOUVEAUX CHAMPS TÂCHE 3 ===
    origine = Column(SQLEnum(TypeOrigineMaintenance), default=TypeOrigineMaintenance.MANUEL)
    alerte_vnc_id = Column(Integer, ForeignKey("alertes_vnc.id", ondelete="SET NULL"), nullable=True)
    score_fiabilite_depart = Column(Float, nullable=True, comment="Score qui a déclenché la maintenance")
    a_genere_alerte = Column(Boolean, default=False, comment="True si cette maintenance a généré une alerte")
    
    # Relations
    bien = relationship("Bien", back_populates="maintenances")
    panne = relationship("Panne", back_populates="maintenances")
    technicien = relationship("Utilisateur", foreign_keys=[id_technicien])
    alerte_vnc = relationship("AlerteVNC", foreign_keys=[alerte_vnc_id])

    def calculer_duree(self) -> int:
        if self.date_debut_reelle and self.date_fin_reelle:
            return (self.date_fin_reelle - self.date_debut_reelle).days
        return 0

    def jours_restants_avant_maintenance(self) -> int:
        if self.date_planifiee and self.statut == StatutMaintenance.PLANIFIEE:
            delta = self.date_planifiee - datetime.utcnow()
            return max(0, delta.days)
        return 0

    @property
    def est_en_retard(self) -> bool:
        """Retourne True si la maintenance planifiée est en retard"""
        if self.statut == StatutMaintenance.PLANIFIEE:
            return datetime.utcnow() > self.date_planifiee
        return False

    def demarrer(self):
        self.statut = StatutMaintenance.EN_COURS
        self.date_debut_reelle = datetime.utcnow()

    def terminer(self, rapport: str = None, cout: float = None):
        self.statut = StatutMaintenance.TERMINEE
        self.date_fin_reelle = datetime.utcnow()
        if rapport:
            self.rapport = rapport
        if cout:
            self.cout = cout

    def reporter(self, nouvelle_date: datetime, motif: str = None):
        self.statut = StatutMaintenance.REPORTEE
        self.date_planifiee = nouvelle_date
        if motif:
            self.observation = motif
    
    def generer_alerte(self):
        """Marque cette maintenance comme ayant généré une alerte"""
        self.a_genere_alerte = True