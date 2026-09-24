# backend/app/models/organisation_role_permission.py
# -*- coding: utf-8 -*-
"""
Modèle OrganisationRolePermission — Surcharges de permissions par ONG (Phase 3).
Permet à une ONG d'activer ou désactiver une permission spécifique pour un rôle,
sans modifier les permissions globales par défaut.
"""
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class OrganisationRolePermission(Base):
    __tablename__ = "organisation_role_permissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_role = Column(
        Integer,
        ForeignKey("roles.id_role", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_permission = Column(
        Integer,
        ForeignKey("permissions.id_permission", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    accorde = Column(Boolean, default=True, nullable=False)
    date_modification = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "organisation_id",
            "id_role",
            "id_permission",
            name="uq_org_role_permission",
        ),
    )

    # Relations
    organisation = relationship("Organisation")
    role = relationship("Role")
    permission = relationship("Permission")

    def __repr__(self):
        return (
            f"<OrganisationRolePermission(id={self.id}, org={self.organisation_id}, "
            f"role={self.id_role}, perm={self.id_permission}, accorde={self.accorde})>"
        )
