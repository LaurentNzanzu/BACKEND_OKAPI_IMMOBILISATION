
import enum
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, ForeignKey, Text, DateTime, Float, JSON, Index, text
from ..core.database import Base


class StatutMission(str, enum.Enum):
    BROUILLON = "BROUILLON"
    DEMANDE = "DEMANDE"
    EN_ATTENTE_VALIDATION = "EN_ATTENTE_VALIDATION"
    VALIDEE_LOG = "VALIDEE_LOG"
    VALIDEE_DG = "VALIDEE_DG"
    VALIDEE = "VALIDEE"
    PLANIFIEE = "PLANIFIEE"
    EN_COURS = "EN_COURS"
    TERMINEE = "TERMINEE"
    ANNULEE = "ANNULEE"
    REJETEE = "REJETEE"


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (
        Index(
            "uq_mission_org_numero",
            "organisation_id",
            "numero_mission",
            unique=True,
            postgresql_where=text("numero_mission IS NOT NULL"),
            sqlite_where=text("numero_mission IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(Integer, ForeignKey("organisations.id"), nullable=False, index=True)
    numero_mission = Column(String(100), nullable=True, index=True)
    projet_id = Column(Integer, ForeignKey("projets.id"), nullable=True, index=True)
    type_workflow = Column(String(50), nullable=False, default="MISSION")
    statut = Column(String(50), nullable=False, default=StatutMission.BROUILLON.value)
    description = Column(Text)
    lieu_depart = Column(String(255))
    lieu_arrivee = Column(String(255))
    date_debut = Column(DateTime)
    date_fin = Column(DateTime)
    passagers = Column(JSON, default=list)
    km_depart = Column(Float, nullable=True)
    km_arrivee = Column(Float, nullable=True)
    heure_depart_reelle = Column(DateTime, nullable=True)
    heure_retour_reelle = Column(DateTime, nullable=True)
    observation = Column(Text, nullable=True)
    photo_depart_url = Column(String(500), nullable=True)
    devise = Column(String(10), default="USD", nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)
    cree_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    etape_actuelle_id = Column(Integer, ForeignKey("workflow_etapes.id", ondelete="SET NULL"), nullable=True)
    motif_rejet = Column(Text, nullable=True)
    valide_par = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    date_validation = Column(DateTime, nullable=True)

    projet = relationship("Projet", back_populates="missions")
    createur = relationship("Utilisateur", foreign_keys=[cree_par])
    validateur = relationship("Utilisateur", foreign_keys=[valide_par])
    etape_actuelle = relationship("WorkflowEtape", foreign_keys=[etape_actuelle_id])
    affectations = relationship("AffectationMission", back_populates="mission", cascade="all, delete-orphan")
    trajets = relationship("Trajet", back_populates="mission", cascade="all, delete-orphan")

    # Propriétés de compatibilité et d'accès rapide
    @property
    def motif(self) -> str | None:
        return self.description

    @motif.setter
    def motif(self, value: str | None):
        self.description = value

    @property
    def destination(self) -> str | None:
        return self.lieu_arrivee

    @destination.setter
    def destination(self, value: str | None):
        self.lieu_arrivee = value

    @property
    def date_depart_prevue(self) -> datetime | None:
        return self.date_debut

    @property
    def date_retour_prevue(self) -> datetime | None:
        return self.date_fin

    @property
    def affectation_active(self):
        for aff in self.affectations or []:
            if aff.statut not in ("ANNULEE", "REJETEE"):
                return aff
        return None

    @property
    def chauffeur_id(self):
        aff = self.affectation_active
        return aff.chauffeur_id if aff else None

    @property
    def vehicule_id(self):
        aff = self.affectation_active
        return aff.vehicule_id if aff else None

    @property
    def chauffeur(self):
        aff = self.affectation_active
        return aff.chauffeur if aff else None

    @property
    def vehicule(self):
        aff = self.affectation_active
        return aff.vehicule if aff else None