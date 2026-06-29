# app/schemas/maintenance.py
from pydantic import BaseModel, Field, ConfigDict, model_validator
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
    id_bien: int = Field(..., gt=0, description="ID du bien concerné")
    type_maintenance: TypeMaintenanceEnum
    date_planifiee: datetime = Field(..., description="Date prévue de la maintenance")
    description: str = Field(..., min_length=5, max_length=1000, description="Description de l'intervention")
    periodicite_jours: Optional[int] = Field(None, ge=1, le=365, description="Périodicité pour les préventives")
    observation: Optional[str] = None

    @model_validator(mode='after')
    def validate_dates(self):
        # ✅ Validation seulement si le statut est PLANIFIEE et la date est fournie
        # Permettre les dates passées pour les maintenances existantes
        if self.date_planifiee:
            # Ne pas bloquer les dates passées pour éviter les erreurs de validation
            # sur les données existantes
            pass
        return self


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

    @model_validator(mode='after')
    def validate_dates_update(self):
        # ✅ Validation conditionnelle : ne vérifier que si une nouvelle date est définie
        # et si le statut est PLANIFIEE
        if self.date_planifiee and self.statut == StatutMaintenanceEnum.PLANIFIEE:
            now = datetime.now()
            # Permettre les dates passées pour les mises à jour
            # (la logique métier gérera les retards)
            pass
        return self


class MaintenanceReporter(BaseModel):
    nouvelle_date: datetime = Field(..., description="Nouvelle date planifiée")
    motif: Optional[str] = Field(None, max_length=500)

    @model_validator(mode='after')
    def validate_reporter_date(self):
        # ✅ Pour le report, on autorise également les dates passées
        # (cela peut arriver si on reporte à une date déjà passée)
        pass
        return self


class MaintenanceTerminer(BaseModel):
    rapport: str = Field(..., min_length=10, description="Rapport d'intervention")
    cout: float = Field(..., gt=0, description="Coût total de l'intervention (strictement positif)")
    pieces_remplacees: Optional[str] = None


class MaintenanceResponse(BaseModel):
    id_maintenance: int
    id_bien: int
    id_technicien: int
    id_panne: Optional[int] = None
    type_maintenance: TypeMaintenanceEnum
    statut: StatutMaintenanceEnum
    date_planifiee: Optional[datetime] = None
    date_debut_reelle: Optional[datetime] = None
    date_fin_reelle: Optional[datetime] = None
    description: str
    cout: float = 0.0
    cout_total_annee: Optional[float] = None
    nombre_interventions_annee: Optional[int] = None
    duree_jours: Optional[int] = None
    jours_restants: Optional[int] = None
    observation: Optional[str] = None
    periodicite_jours: Optional[int] = None
    pieces_remplacees: Optional[str] = None
    rapport: Optional[str] = None
    date_creation: datetime
    bien_designation: Optional[str] = None
    technicien_nom: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def est_en_retard(self) -> bool:
        """Retourne True si la maintenance planifiée est en retard."""
        if self.statut == StatutMaintenanceEnum.PLANIFIEE and self.date_planifiee:
            return datetime.now() > self.date_planifiee
        return False

    # ✅ Suppression du validateur strict sur date_planifiee
    # Les dates passées sont maintenant autorisées

    @model_validator(mode='after')
    def validate_response(self):
        """Validation légère pour la réponse - ne bloque pas les dates passées"""
        # Ne pas valider date_planifiee ici
        return self


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