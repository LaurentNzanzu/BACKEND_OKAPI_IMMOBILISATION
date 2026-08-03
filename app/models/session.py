from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from ..core.database import Base


class SessionUtilisateur(Base):
    """
    Modèle de session utilisateur pour la traçabilité et le contrôle des sessions.
    """
    __tablename__ = "sessions_utilisateurs"

    # === IDENTIFIANT PRINCIPAL ===
    id = Column(Integer, primary_key=True, index=True)
    session_uuid = Column(
        String(36), 
        unique=True, 
        nullable=False, 
        index=True,
        default=lambda: str(uuid.uuid4())
    )
    
    # === RELATIONS ===
    user_id = Column(
        Integer, 
        ForeignKey("utilisateurs.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # === TOKENS ===
    refresh_token_hash = Column(String(255), nullable=False, unique=True)
    
    # === FINGERPRINT & CONTEXTE ===
    fingerprint = Column(String(255), nullable=True)  # Hashé
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    
    # === TIMESTAMPS ===
    date_connexion = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    date_derniere_activite = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    date_fin = Column(DateTime(timezone=True), nullable=True)
    
    # === STATUT ===
    est_revoquee = Column(Boolean, nullable=False, default=False)
    
    # === MÉTADONNÉES EXTENSIBLES ===
    session_data = Column(JSON, nullable=True, default={})
    
    # === RELATION AVEC L'UTILISATEUR ===
    utilisateur = relationship("Utilisateur", back_populates="sessions")

    # === INDEX ===
    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_uuid", "session_uuid"),
        Index("idx_sessions_refresh_hash", "refresh_token_hash"),
        Index("idx_sessions_user_active", "user_id", "est_revoquee"),
    )

    def __repr__(self):
        return f"<SessionUtilisateur {self.session_uuid} - User {self.user_id}>"

    def is_active(self) -> bool:
        """Vérifie si la session est active (non révoquée)."""
        return not self.est_revoquee

    def revoke(self):
        """Révoque la session."""
        self.est_revoquee = True
        self.date_fin = datetime.utcnow()

    def update_activity(self):
        """Met à jour la date de dernière activité."""
        self.date_derniere_activite = datetime.utcnow()

    def to_dict(self, include_sensitive=False):
        """Convertit la session en dictionnaire."""
        data = {
            "session_uuid": self.session_uuid,
            "user_id": self.user_id,
            "fingerprint": self.fingerprint,
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "date_connexion": self.date_connexion.isoformat() if self.date_connexion else None,
            "date_derniere_activite": self.date_derniere_activite.isoformat() if self.date_derniere_activite else None,
            "date_fin": self.date_fin.isoformat() if self.date_fin else None,
            "est_revoquee": self.est_revoquee,
            "session_data": self.session_data,
        }
        if include_sensitive:
            data["refresh_token_hash"] = self.refresh_token_hash
        return data