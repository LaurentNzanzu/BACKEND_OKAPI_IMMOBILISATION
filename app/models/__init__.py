# backend/app/models/__init__.py
from .permission import Permission, role_permissions
from .role import Role
from .utilisateur import Utilisateur
from .journal_audit import JournalAudit
from .bien import Bien, EtatBien
from .vehicule import Vehicule
from .machine import Machine
from .ordinateur import Ordinateur
from .composant import Composant
from .localisation import Localisation
from .panne import Panne, PrioritePanne, StatutPanne, TypePanne
from .piece_rechange import PieceRechange
from .besoin import Besoin, StatutBesoin
from .ligne_besoin import LigneBesoin
from .validation import Validation, OrdreValidation, DecisionValidation, TypeValidation
from .maintenance import Maintenance, TypeMaintenance, StatutMaintenance, TypeOrigineMaintenance
from .fourniture_piece import FourniturePiece, StatutFourniture
from .amortissement import Amortissement, MethodeAmortissement, StatutAmortissement
from .ecriture_comptable import EcritureComptable, TypeOperationEnum, StatutEcriture
from .plan_comptable import PlanComptable
from .regles_amortissement import RegleAmortissement, RegleHistorique
from .mouvement_bien import MouvementBien, TypeMouvementEnum
from .notification import Notification
from .audit_log import AuditLog
from .decision_ia import DecisionIA, TypeDecisionEnum
from .fournisseur import Fournisseur
from .budget import Budget
from .caisse import Caisse
from .centre_cout import CentreCout


# === TÂCHE 3 ===
from .journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation
from .alerte_vnc import AlerteVNC, StatutAlerteVNC
from .projection_investissement import ProjectionInvestissement, StatutProjection
from .ordre_remplacement import OrdreRemplacement, StatutOrdreRemplacement
from .piece_justificative import PieceJustificative
from .mouvement_caisse import MouvementCaisse
from .historique_statut_ecriture import HistoriqueStatutEcriture
from .cession import Cession
from .workflow_amortissement import (
    WorkflowValidationAmortissement,
    EtapeWorkflowAmortissement,
    StatutWorkflowAmortissement,
)
from .discussion_concertation import (
    DiscussionConcertation,
    MessageConcertation,
    ValidationConcertation,
    TypeValidationEnum,
    DecisionValidationConcertation,
)
from .type_bien import TypeBien

# === TÂCHE 4 (Sprint 0) ===
from .session import SessionUtilisateur
from .config_inventaire import ConfigInventaire
from .organisation import Organisation, PlanAbonnement, StatutOrganisation
from .abonnement_facturation import AbonnementFacturation, StatutPaiement
from .projet import Projet
from .workflow_etape import WorkflowEtape, TypeWorkflow

# ✅ PHASE 3 — Modèle override des permissions par ONG
from .organisation_role_permission import OrganisationRolePermission
from .taux_change import TauxChange


__all__ = [
    # ===================== Utilisateurs et permissions =====================
    "Permission",
    "role_permissions",
    "Role",
    "Utilisateur",
    "JournalAudit",

    # ===================== Biens =====================
    "Bien",
    "EtatBien",
    "Vehicule",
    "Machine",
    "Ordinateur",
    "Composant",
    "Localisation",
    "TypeBien",

    # ===================== Pannes et maintenances =====================
    "Panne",
    "PrioritePanne",
    "StatutPanne",
    "TypePanne",
    "PieceRechange",
    "Besoin",
    "StatutBesoin",
    "LigneBesoin",
    "Validation",
    "OrdreValidation",
    "DecisionValidation",
    "TypeValidation",
    "Maintenance",
    "TypeMaintenance",
    "StatutMaintenance",
    "TypeOrigineMaintenance",
    "FourniturePiece",
    "StatutFourniture",

    # ===================== Amortissements =====================
    "Amortissement",
    "MethodeAmortissement",
    "StatutAmortissement",
    "RegleAmortissement",
    "RegleHistorique",

    # ===================== Écritures comptables =====================
    "EcritureComptable",
    "TypeOperationEnum",
    "StatutEcriture",
    "PlanComptable",
    "MouvementBien",
    "TypeMouvementEnum",
    "HistoriqueStatutEcriture",
    "MouvementCaisse",
    "PieceJustificative",

    # ===================== Notifications et audit =====================
    "Notification",
    "AuditLog",

    # ===================== IA =====================
    "DecisionIA",
    "TypeDecisionEnum",

    # ===================== Fournisseur, Budget, Caisse =====================
    "Fournisseur",
    "Budget",
    "Caisse",
    "CentreCout",

    # ===================== TÂCHE 3 =====================
    "JournalEvenementImmobilisation",
    "TypeEvenementImmobilisation",
    "AlerteVNC",
    "StatutAlerteVNC",
    "ProjectionInvestissement",
    "StatutProjection",
    "OrdreRemplacement",
    "StatutOrdreRemplacement",
    "Cession",
    "WorkflowValidationAmortissement",
    "EtapeWorkflowAmortissement",
    "StatutWorkflowAmortissement",
    "DiscussionConcertation",
    "MessageConcertation",
    "ValidationConcertation",
    "TypeValidationEnum",
    "DecisionValidationConcertation",

    # ===================== Sessions =====================
    "SessionUtilisateur",

    # ===================== TÂCHE 4 — Sprint 0 =====================
    "ConfigInventaire",
    "Organisation",
    "PlanAbonnement",
    "StatutOrganisation",
    "AbonnementFacturation",
    "StatutPaiement",
    "Projet",
    "WorkflowEtape",
    "TypeWorkflow",

    # ===================== PHASE 3 — Override permissions =====================
    "OrganisationRolePermission",
    "TauxChange"
]