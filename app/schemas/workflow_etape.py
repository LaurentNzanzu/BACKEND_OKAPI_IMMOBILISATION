# app/schemas/workflow_etape.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class TypeWorkflowEnum(str, Enum):
    MISSION = "MISSION"
    RAVITAILLEMENT = "RAVITAILLEMENT"
    INCIDENT = "INCIDENT"


class WorkflowEtapeCreate(BaseModel):
    organisation_id: int = Field(..., gt=0)
    type_workflow: TypeWorkflowEnum
    ordre: int = Field(..., ge=1)
    role_requis: Optional[str] = Field(None, max_length=50)
    permission_requise: Optional[str] = Field(None, max_length=50)
    condition: Optional[dict] = None
    est_optionnelle: bool = False
    actif: bool = True


class WorkflowEtapeUpdate(BaseModel):
    ordre: Optional[int] = Field(None, ge=1)
    role_requis: Optional[str] = None
    permission_requise: Optional[str] = None
    condition: Optional[dict] = None
    est_optionnelle: Optional[bool] = None
    actif: Optional[bool] = None


class WorkflowEtapeResponse(BaseModel):
    id: int
    organisation_id: int
    type_workflow: TypeWorkflowEnum
    ordre: int
    role_requis: Optional[str] = None
    permission_requise: Optional[str] = None
    condition: Optional[dict] = None
    est_optionnelle: bool
    actif: bool
    date_creation: Optional[datetime] = None

    # Champ calculé
    condition_remplie: bool = False

    model_config = ConfigDict(from_attributes=True)