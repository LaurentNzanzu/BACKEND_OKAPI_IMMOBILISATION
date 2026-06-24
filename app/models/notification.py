# backend/app/models/notification.py
import enum
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Table
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from ..core.database import Base

class TypeNotificationEnum(enum.Enum):
    BESOIN_CREE = "BESOIN_CREE"
    BESOIN_VALIDE = "BESOIN_VALIDE"
    BESOIN_REJETE = "BESOIN_REJETE"
    MAINTENANCE_PLANIFIEE = "MAINTENANCE_PLANIFIEE"
    ALERTE_STOCK = "ALERTE_STOCK"
    
    # Nouveaux
    ALERTE_FIN_ECHANCE_MAINTENANCE = "ALERTE_FIN_ECHANCE_MAINTENANCE"
    ALERTE_VNC_ZERO = "ALERTE_VNC_ZERO"
    RAPPEL_AMORTISSEMENT_MANQUANT = "RAPPEL_AMORTISSEMENT_MANQUANT"
    DECISION_IA_HEALTH_SCORE = "DECISION_IA_HEALTH_SCORE"
    DECISION_IA_STRATEGIQUE = "DECISION_IA_STRATEGIQUE"
    DECISION_IA_ACHAT = "DECISION_IA_ACHAT"
    MOUVEMENT_CREE = "MOUVEMENT_CREE"
    AMORTISSEMENT_CALCULE = "AMORTISSEMENT_CALCULE"
    FOURNITURE_EN_ATTENTE = "FOURNITURE_EN_ATTENTE"
    FOURNITURE_VALIDEE = "FOURNITURE_VALIDEE"
    STOCK_INSUFFISANT = "STOCK_INSUFFISANT"
    BIEN_EN_TEST = "BIEN_EN_TEST"
    PANNE_RESOLUE = "PANNE_RESOLUE"


class PrioriteNotificationEnum(enum.Enum):
    INFORMATION = "information"
    IMPORTANTE = "importante"
    CRITIQUE = "critique"

# Table de liaison entre notifications et utilisateurs
notification_user = Table(
    "notification_user",
    Base.metadata,
    Column("id_notification", Integer, ForeignKey("notifications.id_notification", ondelete="CASCADE"), primary_key=True),
    Column("id_utilisateur", Integer, ForeignKey("utilisateurs.id", ondelete="CASCADE"), primary_key=True),
    Column("est_lu", Boolean, default=False),
    Column("date_lecture", DateTime(timezone=True), nullable=True),
    Column("est_archivee", Boolean, default=False, nullable=False),
)

class Notification(Base):
    __tablename__ = "notifications"
    
    id_notification = Column(Integer, primary_key=True, index=True)
    # ⚠️ SUPPRIMEZ id_utilisateur - plus besoin car on utilise la table de liaison
    # id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False)  # À SUPPRIMER
    
    type_notification = Column(SQLEnum(TypeNotificationEnum), nullable=False)
    titre = Column(String(200), nullable=False)
    contenu = Column(Text, nullable=False)
    lien_action = Column(String(500), nullable=True)
    priorite = Column(String(20), default="information", nullable=False)
    date_creation = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relations
    destinataires = relationship("Utilisateur", secondary=notification_user, back_populates="notifications")