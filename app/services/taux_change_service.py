# backend/app/services/taux_change_service.py
# -*- coding: utf-8 -*-
"""
TauxChangeService — Gestion des taux de change (multi-devises)
Phase 4 — Support USD / CDF et autres devises
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import logging

from ..models.taux_change import TauxChange  # Modèle à créer (SQL déjà fourni)
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class TauxChangeService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    # ============================================================
    # 1. CRUD TAUX
    # ============================================================

    def enregistrer_taux(
        self,
        organisation_id: int,
        devise_source: str,
        devise_cible: str,
        taux: float,
        date_taux: Optional[date] = None,
        source: str = "MANUEL",
        user_id: Optional[int] = None,
    ) -> TauxChange:
        """Crée ou met à jour un taux de change."""
        if not devise_source or not devise_cible:
            raise ValueError("devise_source et devise_cible sont obligatoires")
        if taux <= 0:
            raise ValueError("Le taux doit être strictement positif")

        date_taux = date_taux or date.today()
        dev_s = devise_source.strip().upper()
        dev_c = devise_cible.strip().upper()

        existing = (
            self.db.query(TauxChange)
            .filter(
                TauxChange.organisation_id == organisation_id,
                TauxChange.devise_source == dev_s,
                TauxChange.devise_cible == dev_c,
                TauxChange.date_taux == date_taux,
            )
            .first()
        )

        if existing:
            old = float(existing.taux)
            existing.taux = Decimal(str(taux))
            existing.source = source
            existing.utilisateur_id = user_id
            record = existing
            action = "UPDATE"
        else:
            record = TauxChange(
                organisation_id=organisation_id,
                devise_source=dev_s,
                devise_cible=dev_c,
                taux=Decimal(str(taux)),
                date_taux=date_taux,
                source=source,
                utilisateur_id=user_id,
            )
            self.db.add(record)
            action = "CREATE"

        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="taux_change",
                    record_id=record.id,
                    action=f"TAUX_{action}",
                    nouvelles_valeurs={
                        "organisation_id": organisation_id,
                        "devise_source": dev_s,
                        "devise_cible": dev_c,
                        "taux": float(taux),
                        "date_taux": date_taux.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit taux change échoué : {e}")

        return record

    def obtenir_taux(
        self,
        organisation_id: int,
        devise_source: str,
        devise_cible: str,
        date_reference: Optional[date] = None,
    ) -> Optional[TauxChange]:
        """Récupère le taux le plus récent ≤ date_reference."""
        if not devise_source or not devise_cible:
            return None
        dev_s = devise_source.strip().upper()
        dev_c = devise_cible.strip().upper()

        if dev_s == dev_c:
            return None  # Pas de conversion nécessaire

        date_reference = date_reference or date.today()

        return (
            self.db.query(TauxChange)
            .filter(
                TauxChange.organisation_id == organisation_id,
                TauxChange.devise_source == dev_s,
                TauxChange.devise_cible == dev_c,
                TauxChange.date_taux <= date_reference,
            )
            .order_by(desc(TauxChange.date_taux))
            .first()
        )

    def convertir(
        self,
        organisation_id: int,
        montant: float,
        devise_source: str,
        devise_cible: str,
        date_reference: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Convertit un montant. Si devise_source == devise_cible → identité.
        Sinon, cherche le taux + applique.
        Retourne : {montant_origine, montant_converti, taux, devise_source, devise_cible, date_taux}
        """
        dev_s = (devise_source or "").strip().upper()
        dev_c = (devise_cible or "").strip().upper()

        if dev_s == dev_c:
            return {
                "montant_origine": montant,
                "montant_converti": montant,
                "taux": 1.0,
                "devise_source": dev_s,
                "devise_cible": dev_c,
                "date_taux": (date_reference or date.today()).isoformat(),
                "source": "IDENTITE",
            }

        taux_record = self.obtenir_taux(organisation_id, dev_s, dev_c, date_reference)
        if not taux_record:
            raise ValueError(
                f"Aucun taux de change trouvé pour {dev_s} → {dev_c} "
                f"(organisation #{organisation_id}) à la date {date_reference or date.today()}"
            )

        taux = float(taux_record.taux)
        montant_converti = float(
            (Decimal(str(montant)) * Decimal(str(taux))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )

        return {
            "montant_origine": montant,
            "montant_converti": montant_converti,
            "taux": taux,
            "devise_source": dev_s,
            "devise_cible": dev_c,
            "date_taux": taux_record.date_taux.isoformat(),
            "source": taux_record.source,
        }

    def lister_taux(
        self,
        organisation_id: int,
        devise_source: Optional[str] = None,
        devise_cible: Optional[str] = None,
        limit: int = 100,
    ) -> List[TauxChange]:
        query = self.db.query(TauxChange).filter(TauxChange.organisation_id == organisation_id)
        if devise_source:
            query = query.filter(TauxChange.devise_source == devise_source.upper())
        if devise_cible:
            query = query.filter(TauxChange.devise_cible == devise_cible.upper())
        return query.order_by(desc(TauxChange.date_taux)).limit(limit).all()