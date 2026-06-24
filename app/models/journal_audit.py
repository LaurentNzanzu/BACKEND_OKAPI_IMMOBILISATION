# -*- coding: utf-8 -*-
"""
Modèle pour le journal d'audit - Traçabilité des actions
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class JournalAudit(Base):
    """
    Table de journalisation pour tracer toutes les actions du système
    """
    __tablename__ = "journal_audit"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # ⚠️ ForeignKey vers utilisateurs.id (pas id_utilisateur dans Utilisateur)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True, index=True)
    
    table_concernee = Column(String(100), nullable=False, index=True)
    id_enregistrement = Column(Integer, nullable=True)
    action = Column(String(20), nullable=False, index=True)
    
    anciennes_valeurs = Column(JSON, nullable=True)
    nouvelles_valeurs = Column(JSON, nullable=True)
    
    date_action = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    adresse_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # === Relations ===
    # ⚠️ back_populates doit correspondre au nom dans Utilisateur.audit_logs
    utilisateur = relationship(
        "Utilisateur",
        back_populates="audit_logs",
        lazy="joined"
    )
    
    def __repr__(self):
        return f"<JournalAudit(id={self.id}, action='{self.action}')>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.id_utilisateur,
            "table": self.table_concernee,
            "record_id": self.id_enregistrement,
            "action": self.action,
            "old_values": self.anciennes_valeurs,
            "new_values": self.nouvelles_valeurs,
            "timestamp": self.date_action.isoformat() if self.date_action else None,
            "ip": self.adresse_ip
        }