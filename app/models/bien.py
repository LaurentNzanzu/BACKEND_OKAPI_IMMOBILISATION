# backend/app/models/bien.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Enum, Numeric, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from ..core.database import Base

class EtatBien(enum.Enum):
    NEUF = "NEUF"
    BON = "BON"
    USAGE = "USAGE"
    PANNE = "PANNE"
    REFORME = "REFORME"
    MAINTENANCE = "MAINTENANCE"
    EN_TEST = "EN_TEST"


class StatutComptable(enum.Enum):
    ACTIF = "ACTIF"
    EN_AMORTISSEMENT = "EN_AMORTISSEMENT"
    EN_DEPRECIATION = "EN_DEPRECIATION"
    CEDE = "CEDE"
    MIS_AU_REBUT = "MIS_AU_REBUT"


class Bien(Base):
    __tablename__ = "biens"
    
    id_bien = Column(Integer, primary_key=True, index=True)
    qr_code = Column(String(100), unique=True, index=True)
    date_acquisition = Column(Date)
    prix_acquisition = Column(Numeric(10, 2))
    etat = Column(Enum(EtatBien), default=EtatBien.NEUF)
    localisation = Column(String(200))
    description = Column(String(500))
    image = Column(String(500))
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_sortie = Column(DateTime, nullable=True)
    date_retour = Column(DateTime, nullable=True)
    statut_comptable = Column(String(30), default="ACTIF")
    cumul_amortissement = Column(Numeric(15, 2), default=0)
    cumul_depreciation = Column(Numeric(15, 2), default=0)
    
    # === NOUVEAUX CHAMPS PHASE 1 ===
    mode_paiement = Column(String(20), default="credit", nullable=False)
    fournisseur_id = Column(Integer, ForeignKey("fournisseurs.id", ondelete="SET NULL"), nullable=True)
    
    # === PHASE 7 - RELATION AMORTISSEMENTS ===
    amortissements = relationship(
        "Amortissement", 
        back_populates="bien", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # === PHASE 4 - RELATIONS PANNES ===
    pannes = relationship(
        "Panne", 
        back_populates="bien", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # === PHASE 3 - RELATION COMPOSANTS ===
    composants = relationship(
        "Composant", 
        back_populates="bien", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # === PHASE 5 - RELATION MAINTENANCES ===
    maintenances = relationship(
        "Maintenance", 
        back_populates="bien", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # === PHASE 7 - RELATION ECRITURES COMPTABLES ===
    ecritures_comptables = relationship(
        "EcritureComptable", 
        back_populates="bien", 
        cascade="all, delete-orphan",
        lazy="select"
    )

    mouvements = relationship(
        "MouvementBien", 
        back_populates="bien", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    decisions_ia = relationship("DecisionIA", back_populates="bien", cascade="all, delete-orphan")
    
    # === RELATION FOURNISSEUR ===
    fournisseur = relationship("Fournisseur", back_populates="biens", foreign_keys=[fournisseur_id])
    
    # Discriminator pour l'héritage (Phase 2)
    type_bien = Column(String(50))
    
    __mapper_args__ = {
        "polymorphic_identity": "bien",
        "polymorphic_on": type_bien
    }
    
    def calcul_age(self) -> int:
        """Calcule l'âge du bien en années"""
        from datetime import date
        return date.today().year - self.date_acquisition.year
    
    def changer_etat(self, nouvel_etat: EtatBien):
        """Change l'état du bien"""
        self.etat = nouvel_etat
    
    def est_en_panne(self) -> bool:
        """Vérifie si le bien est en panne"""
        return self.etat == EtatBien.PANNE