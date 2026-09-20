# app/schemas/permission.py
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional


class PermissionBase(BaseModel):
    nom: str = Field(..., max_length=100, description="Code unique de la permission (ex: MISSION_CREATE)")
    description: Optional[str] = Field(None, max_length=255, description="Description de la permission")
    module: str = Field(..., max_length=50, description="Module (ex: BIENS, FLOTTE, MISSIONS)")
    action: str = Field(..., max_length=20, description="Action (ex: CREATE, READ, UPDATE, DELETE)")
    actif: bool = Field(True, description="Statut actif de la permission")


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=255)
    module: Optional[str] = Field(None, max_length=50)
    action: Optional[str] = Field(None, max_length=20)
    actif: Optional[bool] = None


class PermissionResponse(BaseModel):
    """Schéma de réponse pour une permission."""
    id_permission: int
    nom: str
    description: Optional[str] = None
    module: str
    action: str
    actif: bool = True

    model_config = ConfigDict(from_attributes=True)


class RolePermissionAssign(BaseModel):
    permission_ids: List[int] = Field(
        ...,
        min_length=1,
        description="Liste des IDs de permissions à attribuer/révoquer",
    )


class RolePermissionAssignCode(BaseModel):
    permission_code: str = Field(
        ...,
        description="Code unique de la permission à attribuer/révoquer (ex: MISSION_CREATE)",
    )