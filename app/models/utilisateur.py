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
    id = Column(Integer, primary_key=True, index=True)

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

    # Relation vers JournalAudit
    audit_logs = relationship(
        "JournalAudit",
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        lazy="select"
    )

    # Relation vers MouvementBien
    mouvements_realises = relationship(
        "MouvementBien",
        back_populates="utilisateur",
        foreign_keys="[MouvementBien.id_utilisateur]",
        lazy="select"
    )

    # Relation vers DecisionIA
    decisions_ia = relationship("DecisionIA", back_populates="utilisateur", cascade="all, delete-orphan")

    # Relation vers Notification
    notifications = relationship("Notification", secondary="notification_user", back_populates="destinataires")

    # Relation vers FourniturePiece
    fournitures_validees = relationship("FourniturePiece", back_populates="magasinier")

    # === SESSIONS ===
    sessions = relationship(
        "SessionUtilisateur",
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    # ❌ SUPPRIMER CETTE LIGNE (car elle cause l'erreur)
    # permissions = relationship("Permission", secondary="utilisateur_permissions", lazy="selectin")

    def __repr__(self):
        return f"<Utilisateur {self.email}>"

    def get_active_sessions(self, db_session=None):
        """Récupère les sessions actives de l'utilisateur."""
        if db_session:
            return db_session.query(self.sessions).filter(
                self.sessions.est_revoquee == False
            ).all()
        return self.sessions.filter_by(est_revoquee=False)

    def get_all_sessions(self, db_session=None):
        """Récupère toutes les sessions de l'utilisateur."""
        if db_session:
            return db_session.query(self.sessions).all()
        return self.sessions.all()

    def revoke_all_sessions(self, db_session=None, exclude_uuid=None):
        """Révoque toutes les sessions de l'utilisateur."""
        sessions = self.get_active_sessions(db_session)
        revoked_count = 0
        for session in sessions:
            if exclude_uuid and session.session_uuid == exclude_uuid:
                continue
            session.revoke()
            revoked_count += 1
        if db_session:
            db_session.commit()
        return revoked_count

    def count_active_sessions(self, db_session=None):
        """Compte le nombre de sessions actives de l'utilisateur."""
        if db_session:
            return db_session.query(self.sessions).filter(
                self.sessions.est_revoquee == False
            ).count()
        return self.sessions.filter_by(est_revoquee=False).count()

    def has_permission(self, permission_name: str) -> bool:
        """Vérifie si l'utilisateur a une permission spécifique via son rôle."""
        if not self.role:
            return False
        return self.role.has_permission(permission_name)

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