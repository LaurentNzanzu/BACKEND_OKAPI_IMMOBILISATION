from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from ..models.bien import Bien
from ..models.panne import Panne, StatutPanne
from ..models.utilisateur import Utilisateur
import datetime

class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    # ═══ MODIF 5.22 — Filtre organisation_id + cache scopé ONG ═══
    def get_global_summary(self, organisation_id: Optional[int] = None) -> dict:
        from ..core.redis import CacheService
        from ..core.database import LocalCache
        from sqlalchemy import text

        cache_key = f"dashboard:global_summary:org_{organisation_id}" if organisation_id is not None else "dashboard:global_summary:all"
        cached_data = LocalCache.get(cache_key) or CacheService.get(cache_key)
        if cached_data:
            return cached_data

        if organisation_id is not None:
            # ── Version scopée par ONG ──
            result = self.db.execute(
                text("""
                    WITH 
                    stats_totaux AS (
                        SELECT COUNT(*) as total_biens FROM biens WHERE organisation_id = :org_id
                    ),
                    stats_pannes AS (
                        SELECT COUNT(*) as pannes_en_cours 
                        FROM pannes 
                        WHERE statut IN ('DECLAREE', 'DIAGNOSTIQUEE', 'EN_ATTENTE_PIECES', 'EN_VALIDATION', 'EN_COURS')
                          AND organisation_id = :org_id
                    ),
                    stats_types AS (
                        SELECT type_bien, COUNT(*) as count 
                        FROM biens 
                        WHERE organisation_id = :org_id
                        GROUP BY type_bien
                    )
                    SELECT 
                        (SELECT total_biens FROM stats_totaux) as total_biens,
                        (SELECT pannes_en_cours FROM stats_pannes) as pannes_en_cours,
                        json_object_agg(COALESCE(type_bien, 'AUTRE'), count) as statistiques_biens
                    FROM stats_types
                """),
                {"org_id": organisation_id}
            ).mappings().first()
        else:
            # ── Version admin plateforme (toutes ONG) ──
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
    # ═══ FIN MODIF 5.22 ═══

    def get_widget_data(self, type_widget: str, id_utilisateur: int, organisation_id: Optional[int] = None) -> Any:
        if type_widget == "kpi_pannes":
            summary = self.get_global_summary(organisation_id=organisation_id)
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