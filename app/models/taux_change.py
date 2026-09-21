from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric, ForeignKey,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class TauxChange(Base):
    """
    Taux de change quotidien par ONG.
    1 devise_source = X devise_cible à une date donnée.
    """
    __tablename__ = "taux_change"

    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    devise_source = Column(String(3), nullable=False)
    devise_cible = Column(String(3), nullable=False)
    taux = Column(Numeric(15, 6), nullable=False)
    date_taux = Column(Date, nullable=False)
    source = Column(String(50), default="MANUEL")
    date_creation = Column(DateTime, default=datetime.utcnow)
    utilisateur_id = Column(
        Integer,
        ForeignKey("utilisateurs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relations
    organisation = relationship("Organisation")
    utilisateur = relationship("Utilisateur")

    # Contraintes
    __table_args__ = (
        UniqueConstraint(
            "organisation_id", "devise_source", "devise_cible", "date_taux",
            name="uq_taux_change_org_devises_date",
        ),
        Index(
            "ix_taux_change_org_devises_date",
            "organisation_id", "devise_source", "devise_cible", "date_taux",
        ),
    )

    def __repr__(self):
        return (
            f"<TauxChange(org={self.organisation_id}, "
            f"{self.devise_source}->{self.devise_cible}={self.taux}, "
            f"date={self.date_taux})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organisation_id": self.organisation_id,
            "devise_source": self.devise_source,
            "devise_cible": self.devise_cible,
            "taux": float(self.taux) if self.taux is not None else None,
            "date_taux": self.date_taux.isoformat() if self.date_taux else None,
            "source": self.source,
            "date_creation": self.date_creation.isoformat() if self.date_creation else None,
            "utilisateur_id": self.utilisateur_id,
        }