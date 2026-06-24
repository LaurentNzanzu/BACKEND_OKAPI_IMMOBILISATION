from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class TypeOperationEnum(enum.Enum):
    DOTATION_AMORTISSEMENT = "DOTATION_AMORTISSEMENT"
    ACQUISITION = "ACQUISITION"
    CESSION = "CESSION"
    REPRISE = "REPRISE"
    REPRISE_DEPRECIATION = "REPRISE_DEPRECIATION"
    DEPRECIATION = "DEPRECIATION"


class StatutEcriture(enum.Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    REJETEE = "REJETEE"
    MODIFIEE = "MODIFIEE"


class EcritureComptable(Base):
    __tablename__ = "ecritures_comptables"
    id_ecriture = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    id_amortissement = Column(Integer, ForeignKey("amortissements.id_amortissement"), nullable=True)
    date_ecriture = Column(DateTime, nullable=False)
    exercice = Column(Integer, nullable=False)
    type_operation = Column(SQLEnum(TypeOperationEnum), nullable=False)
    statut = Column(SQLEnum(StatutEcriture), default=StatutEcriture.BROUILLON)
    libelle = Column(Text)
    compte_debit = Column(String(20), nullable=False)
    compte_credit = Column(String(20), nullable=False)
    montant = Column(Float, nullable=False)
    montant_original = Column(Float, nullable=True)
    motif_modification = Column(Text, nullable=True)
    details_calcul = Column(Text, nullable=True)
    piece_justificative = Column(String(100))
    journal = Column(String(20), nullable=True)
    periode_comptable = Column(String(7), nullable=True)
    reference_id = Column(Integer, nullable=True)
    validee = Column(Boolean, default=False)
    date_creation = Column(DateTime, default=datetime.utcnow)
    cree_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    date_validation = Column(DateTime)
    valide_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    id_validateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    id_modificateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    date_modification = Column(DateTime, nullable=True)

    bien = relationship("Bien", back_populates="ecritures_comptables")
    amortissement = relationship("Amortissement", back_populates="ecritures")
    createur = relationship("Utilisateur", foreign_keys=[cree_par])
    validateur = relationship("Utilisateur", foreign_keys=[id_validateur])
    validateur_par = relationship("Utilisateur", foreign_keys=[valide_par])
    modificateur = relationship("Utilisateur", foreign_keys=[id_modificateur])