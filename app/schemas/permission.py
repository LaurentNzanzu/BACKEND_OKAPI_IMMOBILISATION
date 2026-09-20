# app/schemas/permission.py
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional


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
    """Payload pour attribuer des permissions à un rôle."""
    role_id: int = Field(..., gt=0)
    permission_ids: List[int] = Field(default_factory=list)