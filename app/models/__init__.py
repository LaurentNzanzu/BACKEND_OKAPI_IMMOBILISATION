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
from .validation import Validation, OrdreValidation, DecisionValidation, TypeValidation  # MODIFIÉ
from .maintenance import Maintenance, TypeMaintenance, StatutMaintenance, TypeOrigineMaintenance  # MODIFIÉ
from .fourniture_piece import FourniturePiece, StatutFourniture
from .amortissement import Amortissement, MethodeAmortissement, StatutAmortissement
from .ecriture_comptable import EcritureComptable, TypeOperationEnum, StatutEcriture  # MODIFIÉ
from .plan_comptable import PlanComptable
from .regles_amortissement import RegleAmortissement, RegleHistorique
from .mouvement_bien import MouvementBien, TypeMouvementEnum
from .notification import Notification
from .audit_log import AuditLog
from .decision_ia import DecisionIA, TypeDecisionEnum
from .fournisseur import Fournisseur
from .budget import Budget  # NOUVEAU
from .caisse import Caisse
from .centre_cout import CentreCout

# === NOUVEAUX IMPORTATIONS TÂCHE 3 ===
from .journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation
from .alerte_vnc import AlerteVNC, StatutAlerteVNC
from .projection_investissement import ProjectionInvestissement, StatutProjection
from .ordre_remplacement import OrdreRemplacement, StatutOrdreRemplacement
from .piece_justificative import PieceJustificative
from .mouvement_caisse import MouvementCaisse
from .historique_statut_ecriture import HistoriqueStatutEcriture
from .cession import Cession
from .workflow_amortissement import WorkflowValidationAmortissement, EtapeWorkflowAmortissement, StatutWorkflowAmortissement
from .discussion_concertation import DiscussionConcertation, MessageConcertation, ValidationConcertation, TypeValidationEnum, DecisionValidationConcertation


__all__ = [
    # Gestion des utilisateurs et permissions
    "Permission",
    "role_permissions",
    "Role",
    "Utilisateur",
    "JournalAudit",
    
    # Gestion des biens
    "Bien",
    "EtatBien",
    "Vehicule",
    "Machine",
    "Ordinateur",
    "Composant",
    "Localisation",
    
    # Gestion des pannes et maintenances
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
    "TypeValidation",  # NOUVEAU
    "Maintenance",
    "TypeMaintenance",
    "StatutMaintenance",
    "TypeOrigineMaintenance",  # NOUVEAU TÂCHE 3
    "FourniturePiece",
    "StatutFourniture",
    
    # Amortissements et règles configurables
    "Amortissement",
    "MethodeAmortissement",
    "StatutAmortissement",
    "RegleAmortissement",
    "RegleHistorique",
    
    # Écritures comptables
    "EcritureComptable",
    "TypeOperationEnum",
    "StatutEcriture",
    "PlanComptable",
    "MouvementBien",
    "TypeMouvementEnum",
    
    # Notifications et audit
    "Notification",
    "AuditLog",
    
    # Décision IA
    "DecisionIA",
    "TypeDecisionEnum",
    
    # Fournisseur
    "Fournisseur",
    
    # Budget (NOUVEAU)
    "Budget",
    
    # === NOUVEAUX MODÈLES TÂCHE 3 ===
    # Journal des événements d'immobilisation
    "JournalEvenementImmobilisation",
    "TypeEvenementImmobilisation",
    
    # Alertes VNC (Valeur Nette Comptable)
    "AlerteVNC",
    "StatutAlerteVNC",
    
    # Projections d'investissement
    "ProjectionInvestissement",
    "StatutProjection",
    
    # Ordres de remplacement
    "OrdreRemplacement",
    "StatutOrdreRemplacement",
    "DiscussionConcertation",
    "MessageConcertation",
    "ValidationConcertation"
]