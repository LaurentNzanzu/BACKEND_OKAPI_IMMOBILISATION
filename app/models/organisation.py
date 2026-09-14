# app/models/organisation.py
from sqlalchemy import Column, Integer, String, Date, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class PlanAbonnement(str, enum.Enum):
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class StatutOrganisation(str, enum.Enum):
    ACTIF = "ACTIF"
    SUSPENDU = "SUSPENDU"
    EXPIRE = "EXPIRE"


class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(200), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True, comment="Code court (ex: OKAPI, MSF)")
    email_admin = Column(String(200), nullable=False)
    plan_abonnement = Column(SQLEnum(PlanAbonnement), default=PlanAbonnement.BASIC, nullable=False)
    quota_vehicules = Column(Integer, default=10, nullable=False)
    quota_chauffeurs = Column(Integer, default=10, nullable=False)
    quota_missions_mois = Column(Integer, default=50, nullable=False)
    devise = Column(String(3), default="USD", nullable=False)
    date_debut = Column(Date, nullable=True)
    date_fin = Column(Date, nullable=True)
    statut = Column(SQLEnum(StatutOrganisation), default=StatutOrganisation.ACTIF, nullable=False)
    parametres_json = Column(JSON, default=dict, comment="Workflow, seuils, configs diverses")
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_modification = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    projets = relationship("Projet", back_populates="organisation", cascade="all, delete-orphan")
    abonnements = relationship("AbonnementFacturation", back_populates="organisation", cascade="all, delete-orphan")
    workflow_etapes = relationship("WorkflowEtape", back_populates="organisation", cascade="all, delete-orphan")

    @property
    def est_actif(self) -> bool:
        return self.statut == StatutOrganisation.ACTIF

    @property
    def plan_info(self) -> dict:
        return {
            "plan": self.plan_abonnement.value if self.plan_abonnement else None,
            "quota_vehicules": self.quota_vehicules,
            "quota_chauffeurs": self.quota_chauffeurs,
            "quota_missions_mois": self.quota_missions_mois,
        }