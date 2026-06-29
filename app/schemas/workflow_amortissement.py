# backend/app/schemas/workflow_amortissement.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class VerifierTresorerieRequest(BaseModel):
    tresorerie_disponible: bool = Field(..., description="Vrai si les fonds physiques sont disponibles en caisse")
    commentaire: Optional[str] = Field(None, description="Commentaire ou observation du caissier")


class ValiderDecaissementRequest(BaseModel):
    approuve: bool = Field(..., description="Vrai si le DG approuve le décaissement")
    motif: Optional[str] = Field(None, description="Motif de la décision ou instructions du DG")


class ValiderEcritureRequest(BaseModel):
    piece_justificative_url: Optional[str] = Field(None, description="URL de la pièce justificative attachée")
    commentaire: Optional[str] = Field(None, description="Commentaire final du comptable")


class ValidationWorkflowItem(BaseModel):
    id_workflow: int
    etape: str
    statut: str
    id_validateur: Optional[int] = None
    validateur_nom: Optional[str] = None
    date_validation: Optional[datetime] = None
    commentaire: Optional[str] = None
    piece_justificative_url: Optional[str] = None
    bon_decaissement_pdf: Optional[str] = None

    class Config:
        from_attributes = True


class WorkflowStatusResponse(BaseModel):
    id_amortissement: int
    etape_actuelle: str
    statut_global: str
    historique_validations: List[ValidationWorkflowItem]
