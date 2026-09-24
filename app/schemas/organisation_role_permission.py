from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Optional


class OrganisationRolePermissionCreate(BaseModel):
    """Payload pour créer une surcharge."""
    organisation_id: int = Field(..., gt=0)
    id_role: int = Field(..., gt=0)
    id_permission: int = Field(..., gt=0)
    accorde: bool = True


class OrganisationRolePermissionUpdate(BaseModel):
    """Payload pour modifier une surcharge existante."""
    accorde: bool


class OrganisationRolePermissionResponse(BaseModel):
    """Réponse d'une surcharge."""
    id: int
    organisation_id: int
    id_role: int
    id_permission: int
    accorde: bool
    date_modification: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OverrideBulkRequest(BaseModel):
    """Payload bulk : plusieurs overrides en une seule requête."""
    overrides: List[OrganisationRolePermissionCreate] = Field(default_factory=list)


class PermissionResolutionResponse(BaseModel):
    """
    Réponse de diagnostic : explique comment une permission
    est résolue pour une ONG donnée.
    """
    permission_code: str
    organisation_id: int
    id_role: int
    source: str = Field(
        ...,
        description="override | global_default | not_found"
    )
    accorde: bool
    override_existe: bool = False