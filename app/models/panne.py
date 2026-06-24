from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class PrioritePanne(enum.Enum):
    BASSE = "BASSE"
    MOYENNE = "MOYENNE"
    HAUTE = "HAUTE"
    CRITIQUE = "CRITIQUE"

class StatutPanne(enum.Enum):
    DECLAREE = "DECLAREE"
    DIAGNOSTIQUEE = "DIAGNOSTIQUEE"
    EN_ATTENTE_PIECES = "EN_ATTENTE_PIECES"
    EN_VALIDATION = "EN_VALIDATION"
    EN_COURS = "EN_COURS"
    EN_TEST = "EN_TEST"
    TERMINEE = "TERMINEE"
    ANNULEE = "ANNULEE"

class TypePanne(enum.Enum):
    MECANIQUE = "MECANIQUE"
    ELECTRIQUE = "ELECTRIQUE"
    ELECTRONIQUE = "ELECTRONIQUE"
    LOGICIELLE = "LOGICIELLE"
    STRUCTURELLE = "STRUCTURELLE"
    AUTRE = "AUTRE"

class Panne(Base):
    __tablename__ = "pannes"

    id_panne = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    id_technicien = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    date_declaration = Column(DateTime, default=datetime.utcnow)
    date_debut = Column(DateTime, nullable=True)
    date_fin = Column(DateTime, nullable=True)
    type_panne = Column(SQLEnum(TypePanne), default=TypePanne.AUTRE)
    priorite = Column(SQLEnum(PrioritePanne), default=PrioritePanne.MOYENNE)
    statut = Column(SQLEnum(StatutPanne), default=StatutPanne.DECLAREE)
    description = Column(Text, nullable=False)
    diagnostic = Column(Text, nullable=True)
    solution_apportee = Column(Text, nullable=True)
    cout_total_reparation = Column(Float, default=0.0)

    # Relations
    bien = relationship("Bien", back_populates="pannes")
    technicien = relationship("Utilisateur", foreign_keys=[id_technicien])
    besoins = relationship("Besoin", back_populates="panne", cascade="all, delete-orphan")
    maintenances = relationship("Maintenance", back_populates="panne")

    def calculer_duree(self) -> int:
        """Calcule la durée de la panne en jours"""
        if self.date_debut and self.date_fin:
            return (self.date_fin - self.date_debut).days
        return 0

    def changer_statut(self, nouveau_statut: StatutPanne):
        """Change le statut de la panne"""
        self.statut = nouveau_statut
        if nouveau_statut == StatutPanne.EN_COURS and not self.date_debut:
            self.date_debut = datetime.utcnow()
        elif nouveau_statut == StatutPanne.TERMINEE:
            self.date_fin = datetime.utcnow()