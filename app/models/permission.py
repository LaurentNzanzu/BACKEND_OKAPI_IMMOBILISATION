# backend/app/models/permission.py
# -*- coding: utf-8 -*-
"""
Modèle pour les permissions - Contrôle d'accès granulaire
"""
from sqlalchemy import Column, Integer, String, Boolean, Table, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


# =============================================================================
# TABLE D'ASSOCIATION MANY-TO-MANY : Role ↔ Permission
# =============================================================================
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('id_role', Integer, ForeignKey('roles.id_role', ondelete='CASCADE'), primary_key=True),
    Column('id_permission', Integer, ForeignKey('permissions.id_permission', ondelete='CASCADE'), primary_key=True)
)


# =============================================================================
# CLASSE Permission
# =============================================================================
class Permission(Base):
    """
    Modèle représentant une permission dans le système RBAC.
    Une permission = un module + une action (ex: "biens:create")
    """
    __tablename__ = "permissions"
    
    id_permission = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nom = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    module = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)
    actif = Column(Boolean, default=True)
    
    # ✅ Correction de la relation
    roles = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="selectin"  # ✅ Meilleure performance
    )
    
    def __repr__(self):
        return f"<Permission(id_permission={self.id_permission}, nom='{self.nom}')>"
    
    def to_dict(self):
        return {
            "id": self.id_permission,
            "nom": self.nom,
            "module": self.module,
            "action": self.action,
            "actif": self.actif
        }