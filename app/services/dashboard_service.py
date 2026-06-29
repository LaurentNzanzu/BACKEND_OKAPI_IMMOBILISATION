from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from ..models.bien import Bien
from ..models.panne import Panne, StatutPanne
# from ..models.dashboard_widget import DashboardWidget  # ← À décommenter quand la table existe
from ..models.utilisateur import Utilisateur
# from ..schemas.dashboard import WidgetCreate, WidgetUpdate  # ← À décommenter plus tard
import datetime

class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_global_summary(self) -> dict:
        from ..core.redis import CacheService
        from ..core.database import LocalCache
        from sqlalchemy import text

        cache_key = "dashboard:global_summary"
        cached_data = LocalCache.get(cache_key) or CacheService.get(cache_key)
        if cached_data:
            return cached_data

        # 🔴 UNE SEULE requête CTE qui regroupe tout pour éviter la latence réseau
        result = self.db.execute(
            text("""
                WITH 
                stats_totaux AS (
                    SELECT COUNT(*) as total_biens FROM biens
                ),
                stats_pannes AS (
                    SELECT COUNT(*) as pannes_en_cours 
                    FROM pannes 
                    WHERE statut IN ('DECLAREE', 'DIAGNOSTIQUEE', 'EN_ATTENTE_PIECES', 'EN_VALIDATION', 'EN_COURS')
                ),
                stats_types AS (
                    SELECT type_bien, COUNT(*) as count 
                    FROM biens 
                    GROUP BY type_bien
                )
                SELECT 
                    (SELECT total_biens FROM stats_totaux) as total_biens,
                    (SELECT pannes_en_cours FROM stats_pannes) as pannes_en_cours,
                    json_object_agg(COALESCE(type_bien, 'AUTRE'), count) as statistiques_biens
                FROM stats_types
            """)
        ).mappings().first()

        summary = {
            "total_biens": result["total_biens"] if result else 0,
            "pannes_en_cours": result["pannes_en_cours"] if result else 0,
            "statistiques_biens": result["statistiques_biens"] if result and result["statistiques_biens"] else {}
        }

        LocalCache.set(cache_key, summary, ttl_seconds=600)
        CacheService.set(cache_key, summary, ttl=600)
        return summary

    # Les méthodes suivantes seront décommentées quand la table dashboard_widgets existera
    """
    def get_role_id(self, id_utilisateur: int) -> int:
        user = self.db.query(Utilisateur).filter(Utilisateur.id == id_utilisateur).first()
        if not user:
            raise ValueError("Utilisateur non trouvé")
        return user.role_id

    def get_widgets(self, id_utilisateur: int) -> List[DashboardWidget]:
        id_role = self.get_role_id(id_utilisateur)
        return self.db.query(DashboardWidget).filter(
            DashboardWidget.id_role == id_role,
            DashboardWidget.est_visible == True
        ).order_by(DashboardWidget.position_y, DashboardWidget.position_x).all()

    def create_widget(self, id_utilisateur: int, data: WidgetCreate) -> DashboardWidget:
        id_role = self.get_role_id(id_utilisateur)
        widget = DashboardWidget(
            id_role=id_role,
            type_widget=data.type_widget,
            position_x=data.position_x,
            position_y=data.position_y,
            width=data.width,
            height=data.height,
            options=data.options or {}
        )
        self.db.add(widget)
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def update_widget(self, id_widget: int, id_utilisateur: int, data: WidgetUpdate) -> DashboardWidget:
        id_role = self.get_role_id(id_utilisateur)
        widget = self.db.query(DashboardWidget).filter(
            DashboardWidget.id_widget == id_widget,
            DashboardWidget.id_role == id_role
        ).first()
        if not widget:
            raise ValueError("Widget non trouvé")
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(widget, key, value)
        
        widget.updated_at = datetime.datetime.utcnow()
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def delete_widget(self, id_widget: int, id_utilisateur: int) -> bool:
        id_role = self.get_role_id(id_utilisateur)
        widget = self.db.query(DashboardWidget).filter(
            DashboardWidget.id_widget == id_widget,
            DashboardWidget.id_role == id_role
        ).first()
        if not widget:
            return False
        self.db.delete(widget)
        self.db.commit()
        return True
    """

    def get_widget_data(self, type_widget: str, id_utilisateur: int) -> Any:
        if type_widget == "kpi_pannes":
            summary = self.get_global_summary()
            return {"total": summary["pannes_en_cours"], "en_cours": summary["pannes_en_cours"], "cette_semaine": 0}
        elif type_widget == "validations_attente":
            return {"count": 3, "items": ["Demande #45", "Demande #46", "Demande #47"]}
        elif type_widget == "alertes_stock":
            return {"count": 2, "items": ["Filtre à huile", "Batterie 12V"]}
        elif type_widget == "dernieres_pannes":
            return [
                {"id": 101, "bien": "Toyota Hilux", "date": "2024-05-18", "statut": "DIAGNOSTIQUEE"},
                {"id": 102, "bien": "Machine CNC", "date": "2024-05-17", "statut": "EN_COURS"},
            ]
        return None