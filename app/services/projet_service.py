# backend/app/services/projet_service.py
# -*- coding: utf-8 -*-
"""
ProjetService — Centre de coût bailleur
Sprint 0 — Fondations OKAPI Flotte

Gère les projets (financés par bailleurs), leurs budgets et leur consommation.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from ..models.projet import Projet
from ..models.budget import Budget
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class ProjetService:
    """Service de gestion des projets et de leurs budgets."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    # ============================================================
    # 1. CRUD PROJET
    # ============================================================

    def creer_projet(
        self, data: Dict[str, Any], user_id: Optional[int] = None
    ) -> Projet:
        """Crée un nouveau projet rattaché à une organisation."""
        organisation_id = data.get("organisation_id")
        if not organisation_id:
            raise ValueError("organisation_id est obligatoire")

        code = (data.get("code") or "").strip().upper()
        if not code:
            raise ValueError("Le code du projet est obligatoire")

        # Vérifier l'unicité (code + organisation)
        existing = (
            self.db.query(Projet)
            .filter(
                Projet.organisation_id == organisation_id,
                Projet.code == code,
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"Un projet avec le code '{code}' existe déjà pour cette organisation"
            )

        projet = Projet(
            organisation_id=organisation_id,
            code=code,
            nom=data.get("nom"),
            bailleur=data.get("bailleur"),
            budget_annuel=Decimal(str(data.get("budget_annuel", 0))),
            devise=data.get("devise", "USD"),
            date_debut=data.get("date_debut"),
            date_fin=data.get("date_fin"),
            est_actif=data.get("est_actif", True),
        )
        self.db.add(projet)
        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="projets",
                    record_id=projet.id,
                    new_values={
                        "code": projet.code,
                        "nom": projet.nom,
                        "bailleur": projet.bailleur,
                        "budget_annuel": float(projet.budget_annuel),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit création projet échoué : {e}")

        logger.info(f"Projet créé : {projet.code} - {projet.nom}")
        return projet

    def obtenir_projet(self, projet_id: int) -> Optional[Projet]:
        """Récupère un projet par ID."""
        return self.db.query(Projet).filter(Projet.id == projet_id).first()

    def lister_projets(
        self,
        organisation_id: int,
        est_actif: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[Projet]:
        """Liste les projets d'une organisation."""
        query = self.db.query(Projet).filter(
            Projet.organisation_id == organisation_id
        )

        if est_actif is not None:
            query = query.filter(Projet.est_actif == est_actif)

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                (Projet.nom.ilike(term))
                | (Projet.code.ilike(term))
                | (Projet.bailleur.ilike(term))
            )

        return query.order_by(Projet.code).all()

    def mettre_a_jour(
        self,
        projet_id: int,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Projet:
        """Met à jour un projet."""
        projet = self.obtenir_projet(projet_id)
        if not projet:
            raise ValueError(f"Projet #{projet_id} introuvable")

        old_values = {
            "nom": projet.nom,
            "bailleur": projet.bailleur,
            "budget_annuel": float(projet.budget_annuel),
            "est_actif": projet.est_actif,
        }

        champs_autorises = [
            "nom",
            "bailleur",
            "budget_annuel",
            "devise",
            "date_debut",
            "date_fin",
            "est_actif",
        ]
        for champ in champs_autorises:
            if champ in data and data[champ] is not None:
                if champ == "budget_annuel":
                    setattr(projet, champ, Decimal(str(data[champ])))
                else:
                    setattr(projet, champ, data[champ])

        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_update(
                    user_id=user_id,
                    table_name="projets",
                    record_id=projet.id,
                    old_values=old_values,
                    new_values={
                        "nom": projet.nom,
                        "budget_annuel": float(projet.budget_annuel),
                        "est_actif": projet.est_actif,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit update projet échoué : {e}")

        return projet

    def desactiver(
        self, projet_id: int, user_id: Optional[int] = None
    ) -> Projet:
        """Désactive un projet (soft delete)."""
        projet = self.obtenir_projet(projet_id)
        if not projet:
            raise ValueError(f"Projet #{projet_id} introuvable")

        if not projet.est_actif:
            raise ValueError("Ce projet est déjà désactivé")

        projet.est_actif = False
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="projets",
                    record_id=projet.id,
                    action="DESACTIVATION",
                    nouvelles_valeurs={"est_actif": False},
                )
            except Exception as e:
                logger.warning(f"Audit désactivation projet échoué : {e}")

        logger.info(f"Projet désactivé : {projet.code}")
        return projet

    # ============================================================
    # 2. BUDGET — CALCULS
    # ============================================================

    def budget_consomme(self, projet_id: int, exercice: Optional[int] = None) -> Decimal:
        """
        Calcule le budget consommé sur un projet.
        
        Sources d'agrégation :
        - Budget.montant_utilise (Sprint 0 — indexé par id_projet après migration)
        - Missions + ApprovisionnementsCarburant (Sprint 1/2)
        """
        projet = self.obtenir_projet(projet_id)
        if not projet:
            raise ValueError(f"Projet #{projet_id} introuvable")

        if exercice is None:
            exercice = datetime.utcnow().year

        # Essayer d'abord la table Budget (indexée par id_projet après migration)
        try:
            total_budget = (
                self.db.query(func.coalesce(func.sum(Budget.montant_utilise), 0))
                .filter(
                    Budget.id_projet == projet_id,
                    Budget.exercice == exercice,
                )
                .scalar()
            )
            if total_budget:
                return Decimal(str(total_budget))
        except Exception as e:
            logger.debug(f"Budget.id_projet non disponible : {e}")

        # Fallback : compter via Missions (Sprint 1)
        try:
            from ..models.mission import Mission
            from ..models.approvisionnement_carburant import ApprovisionnementCarburant

            total_missions = (
                self.db.query(
                    func.coalesce(func.sum(Mission.cout_total), 0)
                )
                .filter(Mission.id_projet == projet_id)
                .scalar()
                or 0
            )

            total_carburant = (
                self.db.query(
                    func.coalesce(func.sum(ApprovisionnementCarburant.montant_total), 0)
                )
                .filter(ApprovisionnementCarburant.id_projet == projet_id)
                .scalar()
                or 0
            )

            return Decimal(str(total_missions)) + Decimal(str(total_carburant))

        except ImportError:
            return Decimal("0.00")
        except Exception as e:
            logger.warning(f"Erreur calcul budget consommé : {e}")
            return Decimal("0.00")

    def budget_restant(self, projet_id: int, exercice: Optional[int] = None) -> Decimal:
        """Calcule le budget restant sur un projet."""
        projet = self.obtenir_projet(projet_id)
        if not projet:
            raise ValueError(f"Projet #{projet_id} introuvable")

        consomme = self.budget_consomme(projet_id, exercice)
        budget = Decimal(str(projet.budget_annuel or 0))
        restant = budget - consomme

        return restant if restant > 0 else Decimal("0.00")

    def get_resume_budgetaire(
        self, projet_id: int, exercice: Optional[int] = None
    ) -> Dict[str, Any]:
        """Retourne un résumé budgétaire complet d'un projet."""
        projet = self.obtenir_projet(projet_id)
        if not projet:
            raise ValueError(f"Projet #{projet_id} introuvable")

        if exercice is None:
            exercice = datetime.utcnow().year

        budget = Decimal(str(projet.budget_annuel or 0))
        consomme = self.budget_consomme(projet_id, exercice)
        restant = budget - consomme
        taux = float(consomme / budget * 100) if budget > 0 else 0.0

        return {
            "projet_id": projet.id,
            "code": projet.code,
            "nom": projet.nom,
            "bailleur": projet.bailleur,
            "exercice": exercice,
            "devise": projet.devise,
            "budget_annuel": float(budget),
            "budget_consomme": float(consomme),
            "budget_restant": float(restant) if restant > 0 else 0.0,
            "taux_utilisation": round(taux, 2),
            "est_en_alerte": taux >= 80.0,
            "est_depasse": restant < 0,
        }

    def verifier_disponibilite(
        self, projet_id: int, montant: Decimal, exercice: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Vérifie si un projet peut absorber un montant.
        Utilisé avant d'engager une dépense.
        """
        resume = self.get_resume_budgetaire(projet_id, exercice)
        restant = Decimal(str(resume["budget_restant"]))
        montant = Decimal(str(montant))

        est_disponible = restant >= montant

        return {
            "est_disponible": est_disponible,
            "restant_avant": float(restant),
            "montant_demande": float(montant),
            "restant_apres": float(restant - montant) if est_disponible else 0.0,
            "message": (
                "Budget suffisant"
                if est_disponible
                else f"Budget insuffisant. Restant: {restant} {resume['devise']}"
            ),
        }

    # ============================================================
    # 3. UTILITAIRES
    # ============================================================

    def lister_projets_actifs(self, organisation_id: int) -> List[Projet]:
        """Liste uniquement les projets actifs d'une organisation."""
        return self.lister_projets(organisation_id, est_actif=True)

    def compter_projets(self, organisation_id: int) -> int:
        """Compte le nombre de projets d'une organisation."""
        return (
            self.db.query(func.count(Projet.id))
            .filter(Projet.organisation_id == organisation_id)
            .scalar()
            or 0
        )