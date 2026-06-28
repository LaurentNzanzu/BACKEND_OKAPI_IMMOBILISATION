from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.dashboard_service import DashboardService
from ...schemas.dashboard import WidgetCreate, WidgetUpdate, WidgetResponse, DashboardSummaryResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = DashboardService(db)
    return service.get_global_summary()

@router.get("/widgets", response_model=List[WidgetResponse])
def get_user_widgets(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = DashboardService(db)
    return service.get_widgets(current_user.id)

@router.post("/widgets", response_model=WidgetResponse)
def create_widget(
    widget_data: WidgetCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = DashboardService(db)
    return service.create_widget(current_user.id, widget_data)

@router.put("/widgets/{id_widget}", response_model=WidgetResponse)
def update_widget(
    id_widget: int,
    data: WidgetUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = DashboardService(db)
    try:
        return service.update_widget(id_widget, current_user.id, data)
    except ValueError:
        raise HTTPException(status_code=404, detail="Widget non trouvé")

@router.delete("/widgets/{id_widget}")
def delete_widget(
    id_widget: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = DashboardService(db)
    success = service.delete_widget(id_widget, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Widget non trouvé")
    return {"message": "Widget supprimé"}

@router.get("/data/{type_widget}")
def get_widget_data(
    type_widget: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = DashboardService(db)
    data = service.get_widget_data(type_widget, current_user.id)
    return {"type": type_widget, "data": data}