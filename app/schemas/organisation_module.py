# backend/app/schemas/organisation_module.py
# -*- coding: utf-8 -*-
"""
Schémas Pydantic pour la gestion des modules activables par ONG.
Phase 3 — Fondations SaaS multi-tenant OKAPI Flotte
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional


class ModuleInfo(BaseModel):
    """Métadonnées d'un module du registre."""
    code: str = Field(..., description="Code unique du module")
    libelle: str = Field(..., description="Libellé affiché")
    description: Optional[str] = None
    icone: Optional[str] = None


class ModulesActifsUpdate(BaseModel):
    """Payload pour mettre à jour la liste des modules actifs d'une ONG."""
    modules_actifs: List[str] = Field(default_factory=list)

    @field_validator("modules_actifs")
    @classmethod
    def normaliser(cls, v):
        if not v:
            return []
        return [str(m).strip().upper() for m in v if m and str(m).strip()]


class ModulesActifsResponse(BaseModel):
    """Liste des modules actifs d'une ONG + info de tous les disponibles."""
    modules_actifs: List[str] = Field(default_factory=list)
    modules_disponibles: List[ModuleInfo] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ModulesPlanInfo(BaseModel):
    """Info sur les modules par défaut d'un plan."""
    plan: str
    modules_par_defaut: List[str] = Field(default_factory=list)
    total: int = 0