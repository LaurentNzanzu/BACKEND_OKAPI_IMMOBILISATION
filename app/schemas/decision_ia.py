# backend/app/schemas/decision_ia.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class TypeDecisionEnum(str, Enum):
    HEALTH_SCORE = "HEALTH_SCORE"
    # Ajouter d'autres types si nécessaire

class HealthScoreResponse(BaseModel):
    bien_id: int
    bien_designation: str
    score: float
    statut: str
    valeur_origine: float
    vnc: float
    cout_maintenance_12m: float
    frequence_pannes_12m: int
    age_actuel_ans: float
    duree_vie_totale: float
    recommandation: str
    date_analyse: str # Format ISO 8601 string

    class Config:
        orm_mode = True

# Si le schéma pour DecisionIA n'existe pas ailleurs, le définir ici aussi
class DecisionIACreate(BaseModel):
    id_bien: Optional[int] = None  
    id_piece: Optional[int] = None  
    id_utilisateur: int # Utilisation de 'id_utilisateur' dans le schéma d'entrée
    type_decision: TypeDecisionEnum
    score: Optional[float] = None
    statut: Optional[str] = None
    contenu: dict
    source_modele: Optional[str] = None

class DecisionIARead(DecisionIACreate):
    id: int
    date_creation: datetime
    # Ne pas inclure 'id_utilisateur' ici si le frontend utilise 'id'

class DecisionStrategiqueResponse(BaseModel):
    """
    Réponse de l'analyse stratégique Conserver vs Remplacer.
    """
    bien_id: int
    bien_designation: str
    decision: str = Field(..., description="REMPLACEMENT_RECOMMANDE ou CONSERVATION")
    delai: str = Field(..., description="6_mois ou N/A")
    cout_conserver_annuel: float
    cout_remplacer_annuel: float
    economie_annuelle: float
    raisons: List[str]
    actions_suggerees: List[str]
    date_analyse: datetime = Field(default_factory=datetime.utcnow)
# --- NOUVEAUX Schémas pour l'Assistant IA (Phase 1.4) ---
class AssistantRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Question de l'utilisateur en langage naturel")

class AssistantResponse(BaseModel):
    reponse: str = Field(..., description="Réponse textuelle de l'assistant")
    donnees: List[Dict[str, Any]] = Field(default_factory=list, description="Données brutes associées à la réponse")