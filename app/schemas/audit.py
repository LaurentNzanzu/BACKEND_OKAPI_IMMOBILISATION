from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

class AuditLogBase(BaseModel):
    table_concernee: str
    id_enregistrement: Optional[int] = None
    action: str
    anciennes_valeurs: Optional[Dict[str, Any]] = None
    nouvelles_valeurs: Optional[Dict[str, Any]] = None
    adresse_ip: Optional[str] = None
    user_agent: Optional[str] = None

class AuditLogCreate(AuditLogBase):
    id_utilisateur: Optional[int] = None

class AuditLogResponse(AuditLogBase):
    id_log: int
    id_utilisateur: Optional[int] = None
    date_action: datetime
    utilisateur_nom: Optional[str] = None
    utilisateur_email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class AuditLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogResponse]