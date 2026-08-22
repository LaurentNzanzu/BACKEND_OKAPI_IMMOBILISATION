from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from .auth import UserAuthResponse


class SessionResponse(BaseModel):
    """Réponse complète d'une session."""
    session_uuid: str
    user_id: int
    fingerprint: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    date_connexion: datetime
    date_derniere_activite: datetime
    date_fin: Optional[datetime] = None
    est_revoquee: bool
    session_data: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class SessionSummaryResponse(BaseModel):
    """Résumé d'une session pour l'affichage (sans données sensibles)."""
    session_uuid: str
    date_connexion: datetime
    date_derniere_activite: datetime
    date_fin: Optional[datetime] = None
    est_revoquee: bool
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """Liste paginée de sessions."""
    sessions: List[SessionSummaryResponse]
    total: int
    active_count: Optional[int] = None
    revoked_count: Optional[int] = None


class SessionRevokeRequest(BaseModel):
    """Payload pour la révocation d'une session."""
    reason: Optional[str] = Field(None, description="Raison de la révocation")
    revoke_all: bool = Field(False, description="Révoquer toutes les sessions")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reason": "Appareil perdu",
                "revoke_all": False
            }
        }
    )


class SessionCreateRequest(BaseModel):
    """Payload interne pour la création d'une session."""
    user_id: int
    refresh_token: str
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    fingerprint: Optional[str] = None
    session_data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class SessionStatsResponse(BaseModel):
    """Statistiques des sessions."""
    total_sessions: int
    active_sessions: int
    revoked_sessions: int
    active_percentage: float
    user_stats: List[Dict[str, Any]]


class SessionWithUserResponse(SessionSummaryResponse):
    """Session avec informations utilisateur (pour admin)."""
    user: Optional[UserAuthResponse] = None