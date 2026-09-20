# app/schemas/permission.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Optional


class PermissionResponse(BaseModel):
    id: int
    code: str
    libelle: Optional[str] = None
    module: Optional[str] = None
    date_creation: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RolePermissionAssign(BaseModel):
    role_id: int = Field(..., gt=0)
    permission_ids: List[int] = Field(default_factory=list)