import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Date, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import relationship
from ..core.database import Base


class StatutChauffeur(str, enum.Enum):
    DISPONIBLE = "DISPONIBLE"
    EN_MISSION = "EN_MISSION"
    REPOS = "REPOS"
    INDISPONIBLE = "INDISPONIBLE"


class Chauffeur(Base):
    __tablename__ = "chauffeurs"
    __table_args__ = (
        Index(
            "uq_chauffeur_org_user_actif",
            "organisation_id",
            "utilisateur_id",
            unique=True,
            postgresql_where=text("utilisateur_id IS NOT NULL AND actif = true"),
            sqlite_where=text("utilisateur_id IS NOT NULL AND actif = 1"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(Integer, ForeignKey("organisations.id"), nullable=False, index=True)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True, index=True)
    nom = Column(String(100), nullable=False)
    prenom = Column(String(100), nullable=False)
    telephone = Column(String(50))
    numero_permis = Column(String(100), nullable=False)
    categorie_permis = Column(String(50), nullable=True)
    date_expiration_permis = Column(Date)
    statut = Column(String(50), default=StatutChauffeur.DISPONIBLE.value, nullable=False)
    photo_url = Column(String(500), nullable=True)
    date_embauche = Column(Date, nullable=True)
    observations = Column(Text, nullable=True)
    disponible = Column(Boolean, default=True)
    actif = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    organisation = relationship("Organisation")
    utilisateur = relationship("Utilisateur", foreign_keys=[utilisateur_id])

    # Rétrocompatibilité type_permis <-> categorie_permis
    @property
    def type_permis(self) -> str | None:
        return self.categorie_permis

    @type_permis.setter
    def type_permis(self, value: str | None):
        self.categorie_permis = value

    @property
    def est_actif(self) -> bool:
        return bool(self.actif)

    @est_actif.setter
    def est_actif(self, value: bool):
        self.actif = value