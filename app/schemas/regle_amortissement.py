from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class RegleAmortissementBase(BaseModel):
    categorie_bien: str
    duree_vie_ans: int
    taux_fiscal: float
    coeff_deg_3_4_ans: float = 1.5
    coeff_deg_5_6_ans: float = 2.0
    coeff_deg_7_plus_ans: float = 2.5
    compte_dotation: str = "6812"
    compte_amortissement: Optional[str] = None
    compte_depreciation: str = "2944"
    base_jours_annee: int = 360
    prorata_debut_mois: bool = True
    est_active: bool = True


class RegleAmortissementCreate(RegleAmortissementBase):
    pass


class RegleAmortissementUpdate(BaseModel):
    duree_vie_ans: Optional[int] = None
    taux_fiscal: Optional[float] = None
    coeff_deg_3_4_ans: Optional[float] = None
    coeff_deg_5_6_ans: Optional[float] = None
    coeff_deg_7_plus_ans: Optional[float] = None
    compte_dotation: Optional[str] = None
    base_jours_annee: Optional[int] = None
    est_active: Optional[bool] = None


class RegleAmortissementResponse(RegleAmortissementBase):
    id_regle: int
    date_modification: datetime
    modifie_par: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)