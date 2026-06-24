from pydantic import BaseModel, ConfigDict, Field
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
    id_bien: int
    exercice: int
    methode: MethodeEnum
    date_acquisition: datetime = Field(..., description="Date d'acquisition pour le calcul dégressif")
    date_mise_en_service: datetime = Field(..., description="Date de mise en service pour le calcul linéaire")
    date_debut: Optional[datetime] = Field(None, deprecated=True, description="Déprécié : utiliser date_mise_en_service")
    
    valeur_origine: float
    valeur_residuelle: float = 0.0
    duree_vie_comptable_ans: int
    duree_vie_fiscale_ans: Optional[int] = None
    coefficient_deg: Optional[float] = None
    unites_totales_prevues: Optional[int] = None
    unites_consommees_exercice: Optional[int] = None
    production_totale_prevue: Optional[int] = None
    production_reelle_exercice: Optional[int] = None
    duree_fournisseur: Optional[int] = None
    jours_ouvres_mois: int = 26
    jours_utilisation_annee: Optional[int] = None
    

class AmortissementUpdate(BaseModel):
    statut: Optional[StatutEnum] = None

class AmortissementResponse(BaseModel):
    id_amortissement: int
    id_bien: int
    exercice: int
    methode: MethodeEnum
    annuite_comptable: float
    annuite_fiscale: float
    ecart_a_reintegrer: float
    cumul_comptable: float
    cumul_fiscal: float
    valeur_nette_comptable: float
    valeur_nette_fiscale: float
    statut: StatutEnum
    date_creation: datetime
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
    total_amortissements_comptables: float
    total_amortissements_fiscaux: float
    total_ecarts_a_reintegrer: float
    economie_impot_annuelle: float
    details_par_categorie: dict
    details_par_methode: dict
    alertes_fin_vie: int