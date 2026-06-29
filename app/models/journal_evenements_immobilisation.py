# backend/app/models/journal_evenements_immobilisation.py
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Enum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class TypeEvenementImmobilisation(enum.Enum):
    ACQUISITION = "ACQUISITION"
    REVALUATION = "REVALUATION"
    DEPRECIATION = "DEPRECIATION"
    AMORTISSEMENT = "AMORTISSEMENT"
    PANNE = "PANNE"
    MAINTENANCE = "MAINTENANCE"
    SORTIE_CESSION = "SORTIE_CESSION"
    SORTIE_REBUT = "SORTIE_REBUT"
    TRANSFERT = "TRANSFERT"
    ALERTE_VNC = "ALERTE_VNC"
    SCORE_FIABILITE = "SCORE_FIABILITE"
    REMPLACEMENT = "REMPLACEMENT"

class JournalEvenementImmobilisation(Base):
    __tablename__ = "journal_evenements_immobilisation"
    
    id = Column(Integer, primary_key=True, index=True)
    bien_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False, index=True)
    
    # Type d'événement
    type_evenement = Column(Enum(TypeEvenementImmobilisation), nullable=False)
    
    # Dates
    date_evenement = Column(DateTime, nullable=False, default=datetime.utcnow)
    date_creation = Column(DateTime, default=datetime.utcnow)
    
    # Informations
    libelle = Column(Text, nullable=False)
    montant = Column(Float, default=0.0)
    reference_piece = Column(String(100), nullable=True)  # Facture, bon de commande...
    ancienne_valeur = Column(Float, nullable=True)  # Pour réévaluation
    nouvelle_valeur = Column(Float, nullable=True)  # Pour réévaluation
    
    # Pour les remplacements
    bien_remplace_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="SET NULL"), nullable=True)
    bien_nouveau_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="SET NULL"), nullable=True)
    
    # Utilisateur ayant déclenché l'action
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    
    # Métadonnées additionnelles (JSON stringifié)
    metadonnees = Column(Text, nullable=True)
    
    # Relations
    bien = relationship("Bien", foreign_keys=[bien_id], back_populates="journal_events")
    bien_remplace = relationship("Bien", foreign_keys=[bien_remplace_id],overlaps="events_as_remplace")
    bien_nouveau = relationship("Bien", foreign_keys=[bien_nouveau_id],overlaps="events_as_nouveau")
    utilisateur = relationship("Utilisateur", foreign_keys=[utilisateur_id])
    
    def __repr__(self):
        return f"<JournalEvenement {self.type_evenement} - {self.libelle}>"