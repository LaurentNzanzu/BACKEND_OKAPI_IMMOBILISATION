from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id_log = Column(Integer, primary_key=True, index=True, autoincrement=True)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    table_concernee = Column(String(100), nullable=False, index=True)
    id_enregistrement = Column(Integer, nullable=True)
    action = Column(String(50), nullable=False, index=True)
    anciennes_valeurs = Column(JSON, nullable=True)
    nouvelles_valeurs = Column(JSON, nullable=True)
    date_action = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    adresse_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    utilisateur = relationship("Utilisateur", foreign_keys=[id_utilisateur])

    __table_args__ = (
        Index("idx_audit_user", "id_utilisateur"),
        Index("idx_audit_table_action", "table_concernee", "action"),
        Index("idx_audit_date", "date_action"),
    )