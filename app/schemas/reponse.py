# app/schemas/reponse.py
from typing import Optional, Any, Dict, List, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

T = TypeVar('T')


class ReponseStandard(BaseModel):
    """
    Schéma de réponse API standardisé pour tous les endpoints.
    """
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )
    
    success: bool = Field(default=True, description="Succès de l'opération")
    message: str = Field(default="Opération réussie", description="Message descriptif")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Horodatage de la réponse"
    )
    data: Optional[Any] = Field(default=None, description="Données de la réponse")
    errors: Optional[List[str]] = Field(default=None, description="Liste des erreurs")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="Métadonnées (pagination, etc.)")
    
    @classmethod
    def success_response(
        cls, 
        data: Any = None, 
        message: str = "Opération réussie", 
        meta: Optional[Dict[str, Any]] = None
    ) -> "ReponseStandard":
        """Crée une réponse de succès."""
        return cls(
            success=True,
            message=message,
            data=data,
            meta=meta
        )
    
    @classmethod
    def error_response(
        cls, 
        message: str = "Une erreur est survenue", 
        errors: Optional[List[str]] = None,
        code: Optional[int] = None
    ) -> "ReponseStandard":
        """Crée une réponse d'erreur."""
        meta = {"code": code} if code else None
        return cls(
            success=False,
            message=message,
            errors=errors or [],
            meta=meta
        )
    
    @classmethod
    def paginated_response(
        cls, 
        items: List[Any], 
        total: int, 
        page: int, 
        limit: int, 
        message: str = "Liste récupérée"
    ) -> "ReponseStandard":
        """Crée une réponse paginée."""
        pages = (total + limit - 1) // limit if limit > 0 else 0
        return cls(
            success=True,
            message=message,
            data=items,
            meta={
                "pagination": {
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "pages": pages,
                    "has_next": page < pages,
                    "has_prev": page > 1
                }
            }
        )