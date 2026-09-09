from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ConfigInventaireBase(BaseModel):
    regle: str = Field(..., description="Règle de génération, ex: INV-{YEAR}-{SEQ}")
    longueur_sequence: int = Field(4, ge=1, le=10)
    reset_period: str = Field("annuel", description="annuel, mensuel, jamais")


class ConfigInventaireCreate(ConfigInventaireBase):
    pass


class ConfigInventaireUpdate(ConfigInventaireBase):
    pass


class ConfigInventaireResponse(ConfigInventaireBase):
    id: int
    dernier_numero: int
    date_mise_a_jour: Optional[datetime]

    class Config:
        from_attributes = True