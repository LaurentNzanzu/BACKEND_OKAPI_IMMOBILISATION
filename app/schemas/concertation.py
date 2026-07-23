# app/schemas/concertation.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

from ..models.discussion_concertation import TypeValidationEnum, DecisionValidationConcertation

class MessageConcertationCreate(BaseModel):
    contenu: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[int] = Field(None)

    @field_validator('contenu')
    @classmethod
    def validate_contenu(cls, v):
        if not v or not v.strip():
            raise ValueError("Le contenu du message est obligatoire")
        return v.strip()

class MessageConcertationResponse(BaseModel):
    id: int
    id_discussion: int
    id_utilisateur: int
    nom_validateur: str
    prenom_validateur: str
    role_validateur: str
    contenu: str
    parent_id: Optional[int] = None
    date_creation: datetime
    est_modifie: bool
    date_modification: Optional[datetime] = None
    reponses: List['MessageConcertationResponse'] = []

    class Config:
        from_attributes = True

class ValidationConcertationCreate(BaseModel):
    decision: DecisionValidationConcertation
    commentaire: Optional[str] = Field(None, max_length=1000)

class ValidationConcertationResponse(BaseModel):
    id: int
    id_discussion: int
    id_validateur: int
    nom_validateur: str
    prenom_validateur: str
    role_validateur: str
    decision: DecisionValidationConcertation
    commentaire: Optional[str] = None
    date_decision: datetime

    class Config:
        from_attributes = True

class DiscussionConcertationCreate(BaseModel):
    id_bien: int
    type_validation: TypeValidationEnum
    titre: str = Field(..., min_length=3, max_length=255)

    @field_validator('titre')
    @classmethod
    def validate_titre(cls, v):
        if not v or not v.strip():
            raise ValueError("Le titre est obligatoire")
        return v.strip()

class DiscussionConcertationResponse(BaseModel):
    id: int
    id_bien: int
    bien_designation: str
    type_validation: TypeValidationEnum
    titre: str
    est_active: bool
    date_creation: datetime
    date_cloture: Optional[datetime] = None
    messages: List[MessageConcertationResponse] = []
    validations: List[ValidationConcertationResponse] = []
    statut_validation: str = "EN_ATTENTE"

    class Config:
        from_attributes = True

class DiscussionConcertationStatusResponse(BaseModel):
    id_discussion: int
    id_bien: int
    type_validation: TypeValidationEnum
    validation_dg: bool = False
    validation_comptable: bool = False
    est_valide: bool = False
    date_validation_comptable: Optional[datetime] = None
    date_validation_dg: Optional[datetime] = None
    statut_global: str = "EN_ATTENTE"

    class Config:
        from_attributes = True

MessageConcertationResponse.model_rebuild()