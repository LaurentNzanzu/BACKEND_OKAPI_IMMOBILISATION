# backend/app/schemas/validation.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

from app.models.validation import OrdreValidation, DecisionValidation, TypeValidation

class ValidationBase(BaseModel):
    """Schéma de base pour une validation"""
    id_validateur: int
    ordre_validateur: OrdreValidation
    type_validation: TypeValidation
    id_besoin: Optional[int] = None
    id_bien: Optional[int] = None
    id_budget: Optional[int] = None
    montant_engage: Optional[float] = Field(None, ge=0)
    commentaire: Optional[str] = None

class ValidationCreate(ValidationBase):
    """Schéma pour la création d'une validation"""
    pass

class ValidationApprove(BaseModel):
    """Schéma pour approuver une validation"""
    decision: Optional[DecisionValidation] = Field(
        default=DecisionValidation.APPROUVE,
        description="Décision d'approbation"
    )
    commentaire: Optional[str] = Field(None, max_length=500)
    piece_justificative_url: Optional[str] = None

class ValidationReject(BaseModel):
    """Schéma pour rejeter une validation (motif obligatoire)"""
    decision: Optional[DecisionValidation] = Field(
        default=DecisionValidation.REJETE,
        description="Décision de rejet"
    )
    motif_rejet: str = Field(..., min_length=5, max_length=1000, description="Motif du rejet (obligatoire)")
    commentaire: Optional[str] = Field(None, max_length=500)
    piece_justificative_url: Optional[str] = None

    @field_validator('motif_rejet')
    @classmethod
    def validate_motif_rejet(cls, v):
        if not v or not v.strip():
            raise ValueError("Le motif de rejet est obligatoire")
        return v.strip()

class ValidationDecision(BaseModel):
    """Schéma pour une décision de validation (approbation ou rejet)"""
    decision: DecisionValidation
    motif_rejet: Optional[str] = Field(None, description="Obligatoire si décision = REJETE")
    commentaire: Optional[str] = None
    piece_justificative_url: Optional[str] = None

    @field_validator('motif_rejet')
    @classmethod
    def validate_motif_rejet(cls, v, info):
        decision = info.data.get('decision')
        if decision == DecisionValidation.REJETE and (not v or not v.strip()):
            raise ValueError("Un motif de rejet est obligatoire en cas de rejet")
        return v

class ValidationResponse(BaseModel):
    """Schéma de réponse pour une validation"""
    id_validation: int
    id_validateur: int
    nom_validateur: Optional[str] = None
    ordre_validateur: OrdreValidation
    type_validation: TypeValidation
    decision: DecisionValidation
    motif_rejet: Optional[str] = None
    piece_justificative_url: Optional[str] = None
    montant_engage: Optional[float] = None
    commentaire: Optional[str] = None
    date_validation: datetime
    date_decision: Optional[datetime] = None
    
    # Informations liées
    id_besoin: Optional[int] = None
    id_bien: Optional[int] = None
    id_budget: Optional[int] = None
    besoin_reference: Optional[str] = None
    bien_designation: Optional[str] = None
    budget_centre_cout: Optional[str] = None
    
    class Config:
        from_attributes = True

class ValidationDetailResponse(ValidationResponse):
    """Schéma de réponse détaillé avec toutes les informations"""
    est_terminee: bool
    est_approuvee: bool
    ordre_suivant: Optional[OrdreValidation] = None
    prochains_validateurs: List[dict] = Field(default_factory=list)
    historique_validations: List[dict] = Field(default_factory=list)

class ValidationListResponse(BaseModel):
    """Schéma pour la liste des validations"""
    total: int
    page: int
    page_size: int
    validations: List[ValidationResponse]

class ValidationWorkflowStatus(BaseModel):
    """Schéma pour le statut du workflow de validation"""
    id_besoin: Optional[int] = None
    numero_demande: Optional[str] = None
    statut_actuel: Optional[str] = None
    montant_total: Optional[float] = 0.0
    etape_actuelle: Optional[str] = None
    progression: float = 0.0
    est_termine: bool = False
    est_approuve: bool = False
    etapes: List[dict] = Field(default_factory=list)
    validations: List[dict] = Field(default_factory=list)
    validations_realisees: List[dict] = Field(default_factory=list)
    etapes_suivantes: List[str] = Field(default_factory=list)
    verification_budget: Optional[dict] = Field(None, description="Infos de vérification budgétaire")
    verification_tresorerie: Optional[dict] = Field(None, description="Infos de vérification de trésorerie")
    
    class Config:
        from_attributes = True