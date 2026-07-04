# app/schemas/amortissement.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum


class MethodeEnum(str, Enum):
    LINEAIRE = "LINEAIRE"
    DEGRESSIF = "DEGRESSIF"
    UNITE_PRODUCTION = "UNITE_PRODUCTION"
    COMPOSANTS = "COMPOSANTS"
    SPECIFIQUE_OKAPI = "SPECIFIQUE_OKAPI"


class StatutEnum(str, Enum):
    EN_COURS = "EN_COURS"
    TERMINE = "TERMINE"
    SUSPENDU = "SUSPENDU"


class AmortissementCreate(BaseModel):
    id_bien: int = Field(..., gt=0, description="ID du bien à amortir")
    exercice: int = Field(..., ge=2000, le=2100, description="Exercice comptable")
    methode: MethodeEnum = Field(..., description="Méthode d'amortissement")
    date_acquisition: Optional[datetime] = Field(None, description="Date d'acquisition pour le calcul dégressif")
    date_mise_en_service: Optional[datetime] = Field(None, description="Date de mise en service pour le calcul linéaire")
    date_debut: Optional[datetime] = Field(None, deprecated=True, description="Déprécié : utiliser date_mise_en_service")
    
    valeur_origine: float = Field(..., gt=0, description="Valeur d'origine du bien")
    # ✅ SUPPRESSION DE valeur_residuelle – forcée à 0 selon Tâche 2
    duree_vie_comptable_ans: int = Field(..., ge=1, le=50, description="Durée de vie comptable en années")
    duree_vie_fiscale_ans: Optional[int] = Field(None, ge=1, le=50, description="Durée de vie fiscale en années")
    coefficient_deg: Optional[float] = Field(None, ge=0.5, le=3.0, description="Coefficient dégressif")
    unites_totales_prevues: Optional[int] = Field(None, gt=0, description="Unités totales prévues (UOP)")
    unites_consommees_exercice: Optional[int] = Field(None, ge=0, description="Unités consommées dans l'exercice")
    production_totale_prevue: Optional[int] = Field(None, gt=0, description="Production totale prévue")
    production_reelle_exercice: Optional[int] = Field(None, ge=0, description="Production réelle de l'exercice")
    duree_fournisseur: Optional[int] = Field(None, gt=0, description="Durée fournisseur (OKAPI)")
    jours_ouvres_mois: int = Field(default=26, ge=20, le=31, description="Jours ouvrables par mois")
    jours_utilisation_annee: Optional[int] = Field(None, ge=200, le=365, description="Jours d'utilisation par an")
    
    @field_validator('duree_vie_fiscale_ans')
    @classmethod
    def validate_duree_fiscale(cls, v, info):
        comptable = info.data.get('duree_vie_comptable_ans')
        if v is not None and comptable is not None and v > comptable:
            raise ValueError("La durée fiscale ne peut excéder la durée comptable")
        return v
    
    @field_validator('date_mise_en_service')
    @classmethod
    def validate_dates(cls, v, info):
        acquisition = info.data.get('date_acquisition')
        if acquisition and v and v < acquisition:
            raise ValueError("La date de mise en service ne peut être antérieure à la date d'acquisition")
        return v


class AmortissementUpdate(BaseModel):
    statut: Optional[StatutEnum] = None


class AmortissementResponse(BaseModel):
    id_amortissement: int
    id_bien: int
    exercice: int
    methode: MethodeEnum
    annuite_comptable: Optional[float] = 0.0
    annuite_fiscale: Optional[float] = 0.0
    ecart_a_reintegrer: Optional[float] = 0.0
    cumul_comptable: Optional[float] = 0.0
    cumul_fiscal: Optional[float] = 0.0
    valeur_nette_comptable: Optional[float] = 0.0
    valeur_nette_fiscale: Optional[float] = 0.0
    statut: Optional[StatutEnum] = StatutEnum.EN_COURS
    date_creation: Optional[datetime] = Field(default_factory=datetime.utcnow)
    est_verrouille: bool = False
    date_verrouillage: Optional[datetime] = None
    verrouille_par_id: Optional[int] = None
    verrouille_par_nom: Optional[str] = None
    raison_verrouillage: Optional[str] = None
    est_modifiable: bool = True
    montant_depreciation: Optional[float] = 0.0
    model_config = ConfigDict(from_attributes=True)


class AmortissementListResponse(AmortissementResponse):
    qr_code: Optional[str] = None
    bien_designation: Optional[str] = None
    type_bien: Optional[str] = None


class PlanAmortissementRow(BaseModel):
    annee: int
    vnc_debut_c: float
    vnc_debut_f: float
    annuite_c: float
    annuite_f: float
    ecart: float
    cumul_c: float
    cumul_f: float
    vnc_fin_c: float
    vnc_fin_f: float


class StatistiquesAmortissements(BaseModel):
    total_amortissements_comptables: float = 0.0
    total_amortissements_fiscaux: float = 0.0
    total_ecarts_a_reintegrer: float = 0.0
    economie_impot_annuelle: float = 0.0
    details_par_categorie: dict = Field(default_factory=dict)
    details_par_methode: dict = Field(default_factory=dict)
    alertes_fin_vie: int = 0


class AmortissementValidate(BaseModel):
    id_amortissement: int = Field(..., gt=0)
    valide: bool = Field(..., description="True pour valider, False pour invalider")
    motif: Optional[str] = Field(None, max_length=500, description="Motif si invalidation")
    piece_justificative_url: Optional[str] = None
    
    @field_validator('motif')
    @classmethod
    def validate_motif(cls, v, info):
        valide = info.data.get('valide')
        if not valide and (not v or not v.strip()):
            raise ValueError("Un motif est obligatoire pour invalider un amortissement")
        return v


class AmortissementVerrouiller(BaseModel):
    """Schéma pour le verrouillage d'un amortissement."""
    raison: str = Field(..., min_length=5, max_length=255, description="Raison du verrouillage (obligatoire)")


class AmortissementVerrouilleResponse(BaseModel):
    id_amortissement: int
    id_bien: int
    exercice: int
    est_verrouille: bool
    date_verrouillage: Optional[datetime] = None
    verrouille_par_id: Optional[int] = None
    verrouille_par_nom: Optional[str] = None
    raison_verrouillage: Optional[str] = None
    est_modifiable: bool


class AmortissementValidationStatus(BaseModel):
    id_amortissement: int
    statut_validation: str
    validations: List[dict] = Field(default_factory=list)
    ecritures_generees: List[dict] = Field(default_factory=list)
    montant_total_dotations: float = 0.0
    besoins_tresorerie: float = 0.0
    tresorerie_disponible: bool = False
    validation_caissier: Optional[dict] = None
    validation_dg: Optional[dict] = None


class AmortissementPeriodClosure(BaseModel):
    exercice: int
    periode: str
    total_dotations: float = 0.0
    ecritures_generees: int = 0
    statut: str
    date_cloture: Optional[datetime] = None
    message: Optional[str] = None


class AmortissementTresorerieCheck(BaseModel):
    id_amortissement: int
    montant_dotation: float = 0.0
    tresorerie_disponible: float = 0.0
    est_suffisante: bool = False
    manque: float = 0.0
    recommandation: str = ""


class AmortissementComptableIntegration(BaseModel):
    id_amortissement: int
    id_ecriture_debit: int
    id_ecriture_credit: int
    compte_debit: str
    compte_credit: str
    montant: float = 0.0
    exercice: int
    date_integration: datetime
    integre_par: int
    statut: str
    message: Optional[str] = None


class AmortissementWorkflowResponse(BaseModel):
    """Schéma pour la réponse du workflow d'amortissement"""
    id_amortissement: int
    etape_actuelle: str
    statut_global: str
    historique_validations: List[dict] = Field(default_factory=list)