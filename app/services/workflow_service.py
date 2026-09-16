# backend/app/services/workflow_service.py
# -*- coding: utf-8 -*-
"""
WorkflowService — Workflow administrable multi-ONG
Sprint 0 — Fondations OKAPI Flotte

Permet à l'ADMIN de chaque ONG de configurer son propre circuit
de validation (missions, ravitaillements, incidents) sans redéploiement.
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from ..models.workflow_etape import WorkflowEtape, TypeWorkflow
from ..models.utilisateur import Utilisateur
from ..services.audit_service import AuditService
from ..services.permission_service import PermissionService

logger = logging.getLogger(__name__)


class WorkflowService:
    """Service de gestion du workflow administrable par organisation."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
        self.permission_service = PermissionService(db)

    # ============================================================
    # 1. LECTURE DES ÉTAPES
    # ============================================================

    def obtenir_etapes(
        self,
        type_workflow: str,
        organisation_id: int,
        actif_only: bool = True,
    ) -> List[WorkflowEtape]:
        """Récupère les étapes d'un workflow, triées par ordre."""
        try:
            type_enum = (
                TypeWorkflow[type_workflow.upper()]
                if isinstance(type_workflow, str)
                else type_workflow
            )
        except KeyError:
            raise ValueError(f"Type de workflow invalide : {type_workflow}")

        query = self.db.query(WorkflowEtape).filter(
            WorkflowEtape.organisation_id == organisation_id,
            WorkflowEtape.type_workflow == type_enum,
        )

        if actif_only:
            query = query.filter(WorkflowEtape.actif == True)

        return query.order_by(WorkflowEtape.ordre).all()

    def obtenir_etape(self, etape_id: int) -> Optional[WorkflowEtape]:
        """Récupère une étape par ID."""
        return (
            self.db.query(WorkflowEtape)
            .filter(WorkflowEtape.id == etape_id)
            .first()
        )

    def obtenir_premiere_etape(
        self, type_workflow: str, organisation_id: int
    ) -> Optional[WorkflowEtape]:
        """Retourne la première étape du workflow."""
        etapes = self.obtenir_etapes(type_workflow, organisation_id)
        return etapes[0] if etapes else None

    # ============================================================
    # 2. CRUD ÉTAPES
    # ============================================================

    def creer_etape(
        self, data: Dict[str, Any], user_id: Optional[int] = None
    ) -> WorkflowEtape:
        """Crée une nouvelle étape dans le workflow."""
        organisation_id = data.get("organisation_id")
        if not organisation_id:
            raise ValueError("organisation_id est obligatoire")

        try:
            type_enum = TypeWorkflow[data["type_workflow"].upper()]
        except (KeyError, AttributeError):
            raise ValueError(f"Type de workflow invalide : {data.get('type_workflow')}")

        ordre = data.get("ordre")
        if not ordre or ordre < 1:
            raise ValueError("L'ordre doit être un entier >= 1")

        # Vérifier l'unicité de l'ordre dans ce workflow
        existing = (
            self.db.query(WorkflowEtape)
            .filter(
                WorkflowEtape.organisation_id == organisation_id,
                WorkflowEtape.type_workflow == type_enum,
                WorkflowEtape.ordre == ordre,
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"Une étape avec l'ordre {ordre} existe déjà pour ce workflow"
            )

        etape = WorkflowEtape(
            organisation_id=organisation_id,
            type_workflow=type_enum,
            ordre=ordre,
            role_requis=data.get("role_requis"),
            permission_requise=data.get("permission_requise"),
            condition=data.get("condition"),
            est_optionnelle=data.get("est_optionnelle", False),
            actif=data.get("actif", True),
        )
        self.db.add(etape)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="workflow_etapes",
                    record_id=etape.id,
                    new_values={
                        "type_workflow": type_enum.value,
                        "ordre": ordre,
                        "role_requis": etape.role_requis,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit création étape échoué : {e}")

        logger.info(
            f"Étape workflow créée : {type_enum.value} ordre={ordre} "
            f"pour organisation #{organisation_id}"
        )
        return etape

    def modifier_etape(
        self,
        etape_id: int,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> WorkflowEtape:
        """Modifie une étape du workflow."""
        etape = self.obtenir_etape(etape_id)
        if not etape:
            raise ValueError(f"Étape #{etape_id} introuvable")

        old_values = {
            "ordre": etape.ordre,
            "role_requis": etape.role_requis,
            "permission_requise": etape.permission_requise,
            "condition": etape.condition,
            "est_optionnelle": etape.est_optionnelle,
            "actif": etape.actif,
        }

        champs_autorises = [
            "ordre",
            "role_requis",
            "permission_requise",
            "condition",
            "est_optionnelle",
            "actif",
        ]
        for champ in champs_autorises:
            if champ in data:
                setattr(etape, champ, data[champ])

        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_update(
                    user_id=user_id,
                    table_name="workflow_etapes",
                    record_id=etape.id,
                    old_values=old_values,
                    new_values={
                        "ordre": etape.ordre,
                        "role_requis": etape.role_requis,
                        "actif": etape.actif,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit update étape échoué : {e}")

        return etape

    def supprimer_etape(
        self, etape_id: int, user_id: Optional[int] = None
    ) -> bool:
        """Supprime une étape du workflow."""
        etape = self.obtenir_etape(etape_id)
        if not etape:
            raise ValueError(f"Étape #{etape_id} introuvable")

        old_values = {
            "type_workflow": etape.type_workflow.value,
            "ordre": etape.ordre,
            "role_requis": etape.role_requis,
        }

        self.db.delete(etape)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_delete(
                    user_id=user_id,
                    table_name="workflow_etapes",
                    record_id=etape_id,
                    old_values=old_values,
                )
            except Exception as e:
                logger.warning(f"Audit delete étape échoué : {e}")

        return True

    # ============================================================
    # 3. PROGRESSION DANS LE WORKFLOW
    # ============================================================

    def prochaine_etape(
        self,
        type_workflow: str,
        ordre_actuel: int,
        organisation_id: int,
        contexte: Optional[Dict[str, Any]] = None,
    ) -> Optional[WorkflowEtape]:
        """
        Détermine l'étape suivante du workflow.
        - Ignore les étapes inactives
        - Ignore les étapes optionnelles dont la condition n'est pas remplie
        """
        etapes = self.obtenir_etapes(type_workflow, organisation_id)
        contexte = contexte or {}

        # Chercher l'étape suivante (ordre strictement supérieur)
        etapes_suivantes = [e for e in etapes if e.ordre > ordre_actuel]

        for etape in etapes_suivantes:
            # Étape optionnelle : vérifier la condition
            if etape.est_optionnelle and etape.condition:
                if not self._condition_remplie(etape.condition, contexte):
                    logger.debug(
                        f"Étape optionnelle {etape.ordre} ignorée (condition non remplie)"
                    )
                    continue
            return etape

        return None  # Fin du workflow

    def _condition_remplie(
        self, condition: Dict[str, Any], contexte: Dict[str, Any]
    ) -> bool:
        """
        Évalue une condition JSON.
        Format supporté : {"seuil_montant": 1000, "champ": "montant_total"}
        """
        if not condition:
            return True

        try:
            # Condition type : {"champ": "montant_total", "operateur": ">", "valeur": 1000}
            if "champ" in condition and "valeur" in condition:
                champ = condition["champ"]
                operateur = condition.get("operateur", "==")
                valeur_ref = condition["valeur"]
                valeur_ctx = contexte.get(champ)

                if valeur_ctx is None:
                    return False

                if operateur == ">":
                    return valeur_ctx > valeur_ref
                elif operateur == ">=":
                    return valeur_ctx >= valeur_ref
                elif operateur == "<":
                    return valeur_ctx < valeur_ref
                elif operateur == "<=":
                    return valeur_ctx <= valeur_ref
                elif operateur == "==":
                    return valeur_ctx == valeur_ref
                elif operateur == "!=":
                    return valeur_ctx != valeur_ref

            # Condition type : {"seuil_montant": 1000}
            if "seuil_montant" in condition:
                montant = contexte.get("montant_total", 0)
                return montant >= condition["seuil_montant"]

            # Condition par défaut : non remplie
            return False

        except Exception as e:
            logger.warning(f"Erreur évaluation condition {condition} : {e}")
            return False

    # ============================================================
    # 4. VÉRIFICATION D'AUTORISATION
    # ============================================================

    def verifier_role_autorise(
        self, etape: WorkflowEtape, user: Optional[Utilisateur]
    ) -> bool:
        """
        Vérifie si un utilisateur peut valider une étape :
        - Soit via le rôle requis
        - Soit via la permission requise
        """
        if not user or not etape:
            return False

        # Vérifier par permission granulaire d'abord
        if etape.permission_requise:
            if self.permission_service.hasPermission(user, etape.permission_requise):
                return True

        # Vérifier par rôle
        if etape.role_requis:
            role = getattr(user, "role", None)
            if role:
                role_nom = (getattr(role, "nom", "") or "").strip().upper()
                if role_nom == etape.role_requis.strip().upper():
                    return True
                if role_nom == "ADMIN":
                    return True

        return False

    def obtenir_etapes_pour_user(
        self, type_workflow: str, organisation_id: int, user: Utilisateur
    ) -> List[WorkflowEtape]:
        """Liste les étapes qu'un utilisateur peut valider."""
        etapes = self.obtenir_etapes(type_workflow, organisation_id)
        return [e for e in etapes if self.verifier_role_autorise(e, user)]

    # ============================================================
    # 5. INITIALISATION PAR DÉFAUT
    # ============================================================

    def initialiser_workflow_par_defaut(
        self, organisation_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Crée un workflow par défaut pour une nouvelle organisation :
        - MISSION : DEMANDE → VALIDEE_LOG → VALIDEE_DG (optionnelle) → EN_COURS → TERMINEE
        - RAVITAILLEMENT : SAISIE → VALIDEE_LOG
        - INCIDENT : DECLARE → VALIDE_LOG
        """
        workflows_crees = {"MISSION": 0, "RAVITAILLEMENT": 0, "INCIDENT": 0}

        # Workflow MISSION
        etapes_mission = [
            {"ordre": 1, "role_requis": "RESPONSABLE_PROJET", "permission_requise": "MISSION_CREATE", "est_optionnelle": False},
            {"ordre": 2, "role_requis": "LOGISTICIEN", "permission_requise": "MISSION_VALIDATE_LOG", "est_optionnelle": False},
            {
                "ordre": 3,
                "role_requis": "DG",
                "permission_requise": "MISSION_VALIDATE_DG",
                "est_optionnelle": True,
                "condition": {"seuil_montant": 1000},
            },
        ]

        # Workflow RAVITAILLEMENT
        etapes_ravitaillement = [
            {"ordre": 1, "role_requis": "CHAUFFEUR", "permission_requise": "CARBURANT_SAISIR", "est_optionnelle": False},
            {"ordre": 2, "role_requis": "LOGISTICIEN", "permission_requise": "CARBURANT_VALIDER", "est_optionnelle": False},
        ]

        # Workflow INCIDENT
        etapes_incident = [
            {"ordre": 1, "role_requis": "CHAUFFEUR", "permission_requise": "INCIDENT_DECLARER", "est_optionnelle": False},
            {"ordre": 2, "role_requis": "LOGISTICIEN", "permission_requise": "INCIDENT_VALIDER", "est_optionnelle": False},
        ]

        for type_wf, etapes in [
            ("MISSION", etapes_mission),
            ("RAVITAILLEMENT", etapes_ravitaillement),
            ("INCIDENT", etapes_incident),
        ]:
            for e in etapes:
                try:
                    self.creer_etape(
                        {
                            "organisation_id": organisation_id,
                            "type_workflow": type_wf,
                            **e,
                        },
                        user_id=user_id,
                    )
                    workflows_crees[type_wf] += 1
                except ValueError as err:
                    # Étape déjà existante → ignorer
                    logger.debug(f"Étape {type_wf}/{e['ordre']} déjà existante : {err}")

        logger.info(f"Workflow par défaut créé pour organisation #{organisation_id}")
        return workflows_crees

    def compter_etapes(self, type_workflow: str, organisation_id: int) -> int:
        """Compte les étapes actives d'un workflow."""
        return len(self.obtenir_etapes(type_workflow, organisation_id))