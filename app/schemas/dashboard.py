from pydantic import BaseModel, ConfigDict
from typing import Dict, Any
from datetime import datetime

class DashboardSummaryResponse(BaseModel):
    total_biens: int
    pannes_en_cours: int
    statistiques_biens: Dict[str, int]
    model_config = ConfigDict(from_attributes=True)

class WidgetBase(BaseModel):
    type_widget: str
    position_x: int = 0
    position_y: int = 0
    width: int = 6
    height: int = 4
    est_visible: bool = True
    options: Dict[str, Any] = {}

class WidgetCreate(WidgetBase):
    pass

class WidgetUpdate(BaseModel):
    position_x: int | None = None
    position_y: int | None = None
    width: int | None = None
    height: int | None = None
    est_visible: bool | None = None
    options: Dict[str, Any] | None = None

class WidgetResponse(WidgetBase):
    id_widget: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class WidgetDataResponse(BaseModel):
    type_widget: str
    data: Any