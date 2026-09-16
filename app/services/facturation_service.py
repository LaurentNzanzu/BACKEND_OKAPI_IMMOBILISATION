# backend/app/services/facturation_service.py
# -*- coding: utf-8 -*-
"""
FacturationService — Gestion des factures SaaS
Sprint 0 — Fondations OKAPI Flotte
"""
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
import logging

from ..models.abonnement_facturation import (
    AbonnementFacturation,
    StatutPaiement,
)
from ..models.organisation import Organisation
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class FacturationService:
    """Service de gestion des factures d'abonnement."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    # ============================================================
    # 1. GÉNÉRATION
    # ============================================================

    def generer_facture(
        self,
        organisation_id: int,
        periode: str,
        montant: Optional[float] = None,
        date_echeance: Optional[date] = None,
        user_id: Optional[int] = None,
    ) -> AbonnementFacturation:
        """
        Génère une facture pour une organisation.
        Le format de `periode` doit être "YYYY-MM" (ex: "2026-01").
        """
        organisation = (
            self.db.query(Organisation)
            .filter(Organisation.id == organisation_id)
            .first()
        )
        if not organisation:
            raise ValueError(f"Organisation #{organisation_id} introuvable")

        # Vérifier qu'une facture n'existe pas déjà pour cette période
        existing = (
            self.db.query(AbonnementFacturation)
            .filter(
                AbonnementFacturation.organisation_id == organisation_id,
                AbonnementFacturation.periode == periode,
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"Une facture existe déjà pour {periode} (ID: {existing.id})"
            )

        if montant is None:
            montant = self._montant_par_plan(organisation)

        if date_echeance is None:
            date_echeance = date.today() + timedelta(days=30)

        facture = AbonnementFacturation(
            organisation_id=organisation_id,
            periode=periode,
            montant=Decimal(str(montant)),
            devise=organisation.devise,
            statut_paiement=StatutPaiement.EN_ATTENTE,
            date_echeance=date_echeance,
        )
        self.db.add(facture)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="abonnements_facturation",
                    record_id=facture.id,
                    new_values={
                        "organisation_id": organisation_id,
                        "periode": periode,
                        "montant": float(montant),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit génération facture échoué : {e}")

        logger.info(
            f"Facture générée : {organisation.code} - {periode} ({montant} {organisation.devise})"
        )
        return facture

    # ============================================================
    # 2. PAIEMENT
    # ============================================================

    def enregistrer_paiement(
        self,
        facture_id: int,
        date_paiement: Optional[datetime] = None,
        montant: Optional[float] = None,
        user_id: Optional[int] = None,
    ) -> AbonnementFacturation:
        """Enregistre le paiement d'une facture."""
        facture = (
            self.db.query(AbonnementFacturation)
            .filter(AbonnementFacturation.id == facture_id)
            .first()
        )
        if not facture:
            raise ValueError(f"Facture #{facture_id} introuvable")

        if facture.statut_paiement == StatutPaiement.PAYE:
            raise ValueError("Cette facture est déjà payée")

        facture.statut_paiement = StatutPaiement.PAYE
        facture.date_paiement = date_paiement or datetime.utcnow()

        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="abonnements_facturation",
                    record_id=facture.id,
                    action="PAIEMENT_ENREGISTRE",
                    nouvelles_valeurs={
                        "facture_id": facture.id,
                        "montant": float(facture.montant),
                        "date_paiement": facture.date_paiement.isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit paiement échoué : {e}")

        logger.info(f"Paiement enregistré pour la facture #{facture.id}")
        return facture

    def marquer_en_retard(
        self, facture_id: int, user_id: Optional[int] = None
    ) -> AbonnementFacturation:
        """Marque une facture comme en retard."""
        facture = (
            self.db.query(AbonnementFacturation)
            .filter(AbonnementFacturation.id == facture_id)
            .first()
        )
        if not facture:
            raise ValueError(f"Facture #{facture_id} introuvable")

        facture.statut_paiement = StatutPaiement.RETARD
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="abonnements_facturation",
                    record_id=facture.id,
                    action="FACTURE_EN_RETARD",
                )
            except Exception as e:
                logger.warning(f"Audit marquage retard échoué : {e}")

        return facture

    # ============================================================
    # 3. CONSULTATION
    # ============================================================

    def lister_factures(
        self,
        organisation_id: Optional[int] = None,
        statut: Optional[str] = None,
        date_debut: Optional[date] = None,
        date_fin: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AbonnementFacturation]:
        """Liste les factures avec filtres."""
        query = self.db.query(AbonnementFacturation)

        if organisation_id:
            query = query.filter(
                AbonnementFacturation.organisation_id == organisation_id
            )

        if statut:
            try:
                statut_enum = StatutPaiement[statut.upper()]
                query = query.filter(AbonnementFacturation.statut_paiement == statut_enum)
            except KeyError:
                pass

        if date_debut:
            query = query.filter(AbonnementFacturation.date_creation >= date_debut)

        if date_fin:
            query = query.filter(AbonnementFacturation.date_creation <= date_fin)

        return (
            query.order_by(AbonnementFacturation.date_creation.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def obtenir_facture(self, facture_id: int) -> Optional[AbonnementFacturation]:
        """Récupère une facture par ID."""
        return (
            self.db.query(AbonnementFacturation)
            .filter(AbonnementFacturation.id == facture_id)
            .first()
        )

    def get_resume_facturation(self, organisation_id: int) -> Dict[str, Any]:
        """Résumé de facturation pour une organisation."""
        from sqlalchemy import func

        total_facture = (
            self.db.query(
                func.coalesce(func.sum(AbonnementFacturation.montant), 0)
            )
            .filter(AbonnementFacturation.organisation_id == organisation_id)
            .scalar()
            or 0
        )

        total_paye = (
            self.db.query(
                func.coalesce(func.sum(AbonnementFacturation.montant), 0)
            )
            .filter(
                AbonnementFacturation.organisation_id == organisation_id,
                AbonnementFacturation.statut_paiement == StatutPaiement.PAYE,
            )
            .scalar()
            or 0
        )

        nb_impayees = (
            self.db.query(func.count(AbonnementFacturation.id))
            .filter(
                AbonnementFacturation.organisation_id == organisation_id,
                AbonnementFacturation.statut_paiement != StatutPaiement.PAYE,
            )
            .scalar()
            or 0
        )

        return {
            "organisation_id": organisation_id,
            "total_facture": float(total_facture),
            "total_paye": float(total_paye),
            "total_impaye": float(total_facture - total_paye),
            "nb_factures_impayees": nb_impayees,
            "est_a_jour": nb_impayees == 0,
        }

    # ============================================================
    # 4. EXPORT PDF (stub — à implémenter avec reportlab)
    # ============================================================

    def exporter_facture_pdf(self, facture_id: int) -> Dict[str, Any]:
        """
        Exporte une facture en PDF.
        
        NOTE Sprint 0 : retourne les données structurées.
        L'implémentation reportlab sera faite en Sprint 5+.
        """
        facture = self.obtenir_facture(facture_id)
        if not facture:
            raise ValueError(f"Facture #{facture_id} introuvable")

        organisation = (
            self.db.query(Organisation)
            .filter(Organisation.id == facture.organisation_id)
            .first()
        )

        return {
            "facture_id": facture.id,
            "numero": f"FAC-{facture.id:06d}",
            "organisation": {
                "nom": organisation.nom if organisation else "N/A",
                "code": organisation.code if organisation else "N/A",
                "email": organisation.email_admin if organisation else "N/A",
            },
            "periode": facture.periode,
            "montant": float(facture.montant),
            "devise": facture.devise,
            "statut": facture.statut_paiement.value,
            "date_echeance": facture.date_echeance.isoformat() if facture.date_echeance else None,
            "date_paiement": facture.date_paiement.isoformat() if facture.date_paiement else None,
            "url_pdf": facture.facture_url,
            "message": "Génération PDF à venir (Sprint 5+)",
        }

    # ============================================================
    # 5. UTILITAIRES
    # ============================================================

    def _montant_par_plan(self, organisation: Organisation) -> float:
        """Calcule le montant mensuel selon le plan."""
        tarifs = {"BASIC": 99.0, "PRO": 299.0, "ENTERPRISE": 999.0}
        plan = (
            organisation.plan_abonnement.value
            if organisation.plan_abonnement
            else "BASIC"
        )
        return tarifs.get(plan, 99.0)

    def marquer_retards_en_masse(self) -> int:
        """Marque toutes les factures échues non payées comme RETARD."""
        aujourd_hui = date.today()
        factures = (
            self.db.query(AbonnementFacturation)
            .filter(
                AbonnementFacturation.statut_paiement == StatutPaiement.EN_ATTENTE,
                AbonnementFacturation.date_echeance < aujourd_hui,
            )
            .all()
        )

        for f in factures:
            f.statut_paiement = StatutPaiement.RETARD

        self.db.flush()
        logger.info(f"{len(factures)} factures marquées en retard")
        return len(factures)