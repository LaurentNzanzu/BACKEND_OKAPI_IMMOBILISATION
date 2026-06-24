# backend/app/schemas/maintenance.py
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

class TypeMaintenanceEnum(str, Enum):
    PREVENTIVE = "PREVENTIVE"
    CORRECTIVE = "CORRECTIVE"
    PREDICTIVE = "PREDICTIVE"

class StatutMaintenanceEnum(str, Enum):
    PLANIFIEE = "PLANIFIEE"
    EN_COURS = "EN_COURS"
    TERMINEE = "TERMINEE"
    REPORTEE = "REPORTEE"
    ANNULEE = "ANNULEE"

class MaintenanceBase(BaseModel):
    id_bien: int = Field(..., description="ID du bien concerné")
    type_maintenance: TypeMaintenanceEnum
    date_planifiee: datetime = Field(..., description="Date prévue de la maintenance")
    description: str = Field(..., min_length=5, max_length=1000, description="Description de l'intervention")
    periodicite_jours: Optional[int] = Field(None, ge=1, le=365, description="Périodicité pour les préventives")
    observation: Optional[str] = None

class MaintenanceCreate(MaintenanceBase):
    pass

class MaintenanceUpdate(BaseModel):
    type_maintenance: Optional[TypeMaintenanceEnum] = None
    statut: Optional[StatutMaintenanceEnum] = None
    date_planifiee: Optional[datetime] = None
    description: Optional[str] = None
    observation: Optional[str] = None
    cout: Optional[float] = Field(None, ge=0)
    pieces_remplacees: Optional[str] = None
    rapport: Optional[str] = None

class MaintenanceReporter(BaseModel):
    nouvelle_date: datetime = Field(..., description="Nouvelle date planifiée")
    motif: Optional[str] = Field(None, max_length=500)

class MaintenanceTerminer(BaseModel):
    rapport: str = Field(..., min_length=10, description="Rapport d'intervention")
    cout: float = Field(..., ge=0, description="Coût total de l'intervention")
    pieces_remplacees: Optional[str] = None

class MaintenanceResponse(MaintenanceBase):
    id_maintenance: int
    id_technicien: int
    id_panne: Optional[int] = None
    statut: StatutMaintenanceEnum
    date_debut_reelle: Optional[datetime] = None
    date_fin_reelle: Optional[datetime] = None
    cout: float = 0.0
    cout_total_annee: Optional[float] = None
    nombre_interventions_annee: Optional[int] = None
    duree_jours: Optional[int] = None
    jours_restants: Optional[int] = None
    observation: Optional[str] = None
    pieces_remplacees: Optional[str] = None
    rapport: Optional[str] = None
    date_creation: datetime
    bien_designation: Optional[str] = None
    technicien_nom: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def est_en_retard(self) -> bool:
        """Retourne True si la maintenance planifiée est en retard"""
        if self.statut == StatutMaintenanceEnum.PLANIFIEE and self.date_planifiee:
            return datetime.utcnow() > self.date_planifiee
        return False

class MaintenanceListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    maintenances: List[MaintenanceResponse]

class MaintenanceStatistics(BaseModel):
    total_maintenances: int
    par_type: dict
    par_statut: dict
    cout_total_annee: float
    cout_moyen: float
    taux_realisation: float
    alertes: int