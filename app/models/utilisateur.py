# -*- coding: utf-8 -*-
"""
Modèle représentant un utilisateur du système
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import logging

logger = logging.getLogger(__name__)


class Utilisateur(Base):
    """
    Modèle représentant un utilisateur du système (RBAC)
    """
    __tablename__ = "utilisateurs"

    # === Champs de la table ===
    id = Column(Integer, primary_key=True, index=True)  # Géré via get_next_id()

    # Informations personnelles
    email = Column(String(100), unique=True, nullable=False, index=True)
    nom = Column(String(100), nullable=False)
    post_nom = Column(String(100), nullable=True)
    prenom = Column(String(100), nullable=False)
    telephone = Column(String(20), nullable=True)

    # Sécurité
    mot_de_passe = Column(String(255), nullable=False)  # Hashé
    est_actif = Column(Boolean, default=True, nullable=False)

    # ⚠️ Clé étrangère vers Role : doit pointer vers 'roles.id_role'
    role_id = Column(Integer, ForeignKey("roles.id_role"), nullable=False)

    # === Timestamps ===
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # === Relations ===
    role = relationship("Role", back_populates="utilisateurs")

    @property
    def nom_complet(self) -> str:
        parts = [self.prenom, self.nom, self.post_nom]
        return " ".join([p for p in parts if p]).strip()
    # Dans backend/app/models/utilisateur.py, ajouter :
    #audit_logs = relationship("AuditLog", back_populates="utilisateur", lazy="select")
    
    # Relation vers JournalAudit (avec lazy loading pour éviter les erreurs d'initialisation)
    audit_logs = relationship(
        "JournalAudit",
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        lazy="select"  # ← Chargement différé
    )
    # Relation vers MouvementBien (mouvements réalisés par cet utilisateur)
    mouvements_realises = relationship(
        "MouvementBien",
        back_populates="utilisateur",
        foreign_keys="[MouvementBien.id_utilisateur]",
        lazy="select"
    )
    # Relation vers Notification (notifications reçues par cet utilisateur)
    
    decisions_ia = relationship("DecisionIA", back_populates="utilisateur", cascade="all, delete-orphan")

    notifications = relationship("Notification", secondary="notification_user", back_populates="destinataires")

    fournitures_validees = relationship("FourniturePiece", back_populates="magasinier")

    # === Méthodes utilitaires ===
    def __repr__(self):
        return f"<Utilisateur(id={self.id}, email='{self.email}', role='{self.role.nom if self.role else 'N/A'}')>"

    def to_dict(self, include_sensitive: bool = False):
        data = {
            "id": self.id,
            "email": self.email,
            "nom": self.nom,
            "post_nom": self.post_nom,
            "prenom": self.prenom,
            "telephone": self.telephone,
            "est_actif": self.est_actif,
            "role_id": self.role_id,
            "role_nom": self.role.nom if self.role else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
        if include_sensitive:
            data["mot_de_passe_hash"] = self.mot_de_passe
        return data

    def has_role(self, role_name: str) -> bool:
        return self.role and self.role.nom.upper() == role_name.upper()

    @staticmethod
    def get_next_id(db) -> int:
        try:
            last = db.query(Utilisateur).order_by(Utilisateur.id.desc()).first()
            return last.id + 1 if last and last.id else 1
        except:
            return 1