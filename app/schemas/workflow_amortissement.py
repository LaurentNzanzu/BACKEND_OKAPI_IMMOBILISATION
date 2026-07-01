# backend/app/schemas/workflow_amortissement.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class VerificationTresorerieRequest(BaseModel):
    tresorerie_disponible: Optional[bool] = None
    commentaire: Optional[str] = None


class VerificationTresorerieResponse(BaseModel):
    est_suffisante: bool
    solde_disponible: float
    message: str
    statut_actuel: str


class ValidationDecaissementRequest(BaseModel):
    approuve: bool
    motif: Optional[str] = None
    commentaire: Optional[str] = None


class ValidationDecaissementResponse(BaseModel):
    statut: str
    message: str
    bon_decaissement_url: Optional[str] = None


class ValidationEcritureRequest(BaseModel):
    piece_justificative_url: Optional[str] = None
    commentaire: Optional[str] = None


class WorkflowValidationDetail(BaseModel):
    id_workflow: int
    etape: str
    statut: str
    id_validateur: Optional[int] = None
    validateur_nom: Optional[str] = None
    date_validation: Optional[datetime] = None
    commentaire: Optional[str] = None
    piece_justificative_url: Optional[str] = None
    bon_decaissement_pdf: Optional[str] = None


class WorkflowAmortissementStatus(BaseModel):
    id_amortissement: int
    etape_actuelle: str
    statut_global: str
    historique_validations: List[WorkflowValidationDetail]
