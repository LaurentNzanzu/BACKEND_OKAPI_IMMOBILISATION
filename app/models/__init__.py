from .permission import Permission, role_permissions
from .role import Role
from .utilisateur import Utilisateur
from .journal_audit import JournalAudit
from .bien import Bien, EtatBien
from .vehicule import Vehicule
from .machine import Machine
from .ordinateur import Ordinateur
#from .dashboard_widget import DashboardWidget
from .composant import Composant
from .panne import Panne, PrioritePanne, StatutPanne, TypePanne
from .piece_rechange import PieceRechange
from .besoin import Besoin, StatutBesoin
from .ligne_besoin import LigneBesoin
from .validation import Validation, OrdreValidation, DecisionValidation
from .maintenance import Maintenance, TypeMaintenance, StatutMaintenance
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
    "DashboardWidget",
    "Composant",
    
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
    "Maintenance",
    "TypeMaintenance",
    "StatutMaintenance",
    "FourniturePiece",
    "StatutFourniture",
    
    # Amortissements et règles configurables (RDC/SYSCOHADA)
    "Amortissement",
    "MethodeAmortissement",
    "StatutAmortissement",
    "RegleAmortissement",      # Configuration dynamique des règles
    "RegleHistorique",          # Historique des modifications des règles
    
    # Écritures comptables
    "EcritureComptable",
    "TypeOperationEnum",
    "StatutEcriture",
    "PlanComptable",
    "MouvementBien",
    "TypeMouvementEnum",
    # notifications
    "Notification",
    # audit
    "AuditLog"
    #decision ia
    "DecisionIA", 
    "TypeDecisionEnum",
    #fournisseur
    "Fournisseur"
   

   
]