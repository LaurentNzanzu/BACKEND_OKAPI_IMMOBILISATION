# backend/app/models/role.py
# -*- coding: utf-8 -*-
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import logging

logger = logging.getLogger(__name__)


class Role(Base):
    __tablename__ = "roles"

    id_role = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nom = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    actif = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    permissions = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin"
    )
    
    utilisateurs = relationship(
        "Utilisateur",
        back_populates="role",
        foreign_keys="Utilisateur.role_id",
        lazy="selectin"
    )
    
    

    def __repr__(self):
        return f"<Role(id_role={self.id_role}, nom='{self.nom}', actif={self.actif})>"

    def to_dict(self):
        return {
            "id": self.id_role,
            "nom": self.nom,
            "description": self.description,
            "actif": self.actif,
            "permissions": [p.nom for p in self.permissions] if self.permissions else []
        }

    @staticmethod
    def get_next_id(db) -> int:
        try:
            last = db.query(Role).order_by(Role.id_role.desc()).first()
            return last.id_role + 1 if last and last.id_role else 1
        except:
            return 1