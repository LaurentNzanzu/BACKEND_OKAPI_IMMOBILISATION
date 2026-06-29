# backend/app/core/enums.py
from enum import Enum

class RoleEnum(str, Enum):
    ADMIN = "ADMIN"
    DG = "DG"
    COMPTABLE = "COMPTABLE"
    TECHNICIEN = "TECHNICIEN"
    MAGASINIER = "MAGASINIER"

class StatutBienEnum(str, Enum):
    NEUF = "neuf"
    BON = "bon"
    USAGE = "usage"
    PANNE = "panne"
    REFORME = "reforme"
    MAINTENANCE = "maintenance"

class StatutPanneEnum(str, Enum):
    DECLAREE = "declaree"
    DIAGNOSTIQUEE = "diagnostiquee"
    ENCOURS = "encours"
    ATTENTE = "attente"
    TERMINEE = "terminee"
    ANNULEE = "annulee"

class PrioritePanneEnum(str, Enum):
    BASSE = "basse"
    MOYENNE = "moyenne"
    HAUTE = "haute"
    CRITIQUE = "critique"

class TypeMaintenanceEnum(str, Enum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    PREDICTIVE = "predictive"

class StatutMaintenanceEnum(str, Enum):
    PLANIFIEE = "planifiee"
    ENCOURS = "encours"
    TERMINEE = "terminee"
    REPORTEE = "reportee"
    ANNULEE = "annulee"

class MethodeAmortissementEnum(str, Enum):
    LINEAIRE = "lineaire"
    DEGRESSIF = "degressif"
    VARIABLE = "variable"

class StatutValidationEnum(str, Enum):
    BROUILLON = "brouillon"
    SOUMIS = "soumis"
    EN_VALIDATION = "en_validation"
    VALIDE = "valide"
    REFUSE = "refuse"
    APPROUVE = "approuve"
    REJETE = "rejete"

class OrdreValidationEnum(str, Enum):
    DG = "DG"
    COMPTABLE = "COMPTABLE"
    CAISSE = "CAISSE"

class DecisionValidationEnum(str, Enum):
    VALIDE = "valide"
    REFUSE = "refuse"
    EN_ATTENTE = "en_attente"

class TypeOperationEnum(str, Enum):
    ACQUISITION = "acquisition"
    CESSION = "cession"
    DOTATION = "dotation"
    DEPRECIATION = "depreciation"
    REPRISE = "reprise"

class CanalNotificationEnum(str, Enum):
    SMS = "SMS"
    WHATSAPP = "whatsapp"
    EMAIL = "email"

class ActionAuditEnum(str, Enum):
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    VALIDATE = "VALIDATE"
    REJECT = "REJECT"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"


# ============================================================
# NOUVEAUX ENUMS POUR LA TÂCHE 2
# ============================================================

class TypeValidationEnum(str, Enum):
    """
    Type de validation pour le workflow de la TÂCHE 2.
    Détermine le type d'objet soumis à validation.
    """
    BESOIN = "besoin"
    DEPRECIATION = "depreciation"
    CESSION = "cession"
    AMORTISSEMENT = "amortissement"

class StatutCessionEnum(str, Enum):
    """
    Statut d'une cession pour la TÂCHE 2.
    Suivi du workflow de cession.
    """
    ELIGIBLE = "eligible"
    EN_ATTENTE_VALIDATION = "en_attente_validation"
    EN_COURS = "en_cours"
    ACCORDEE = "accordee"
    REJETEE = "rejetee"
    TERMINEE = "terminee"

class TypeCessionEnum(str, Enum):
    """
    Type de cession.
    """
    COURANTE = "courante"
    NON_COURANTE = "non_courante"
    MISE_AU_REBUT = "mise_au_rebut"

class ModeReglementEnum(str, Enum):
    """
    Mode de règlement pour une cession.
    """
    COMPTANT = "comptant"
    CREDIT = "credit"
    VIREMENT = "virement"
    CHEQUE = "cheque"
    ESPECE = "espece"

class StatutEcritureComptableEnum(str, Enum):
    """
    Statut d'une écriture comptable pour la TÂCHE 2.
    """
    BROUILLON = "brouillon"
    EN_ATTENTE_PAIEMENT = "en_attente_paiement"
    VALIDEE = "validee"
    REJETEE = "rejetee"
    MODIFIEE = "modifiee"

class StatutBudgetEnum(str, Enum):
    """
    Statut d'un budget.
    """
    ACTIF = "actif"
    EPUISE = "epuise"
    BLOQUE = "bloque"
    CLOTURE = "cloture"


# ============================================================
# NOUVEAUX ENUMS POUR LA TÂCHE 3
# ============================================================

class TypeEvenementImmobilisation(str, Enum):
    """
    Type d'événement pour le journal des immobilisations (TÂCHE 3).
    """
    ACQUISITION = "ACQUISITION"
    REVALUATION = "REVALUATION"
    DEPRECIATION = "DEPRECIATION"
    AMORTISSEMENT = "AMORTISSEMENT"
    PANNE = "PANNE"
    MAINTENANCE = "MAINTENANCE"
    SORTIE_CESSION = "SORTIE_CESSION"
    SORTIE_REBUT = "SORTIE_REBUT"
    TRANSFERT = "TRANSFERT"
    ALERTE_VNC = "ALERTE_VNC"
    SCORE_FIABILITE = "SCORE_FIABILITE"
    REMPLACEMENT = "REMPLACEMENT"

class TypeOrigineMaintenance(str, Enum):
    """
    Origine d'une maintenance (TÂCHE 3).
    """
    AUTO = "AUTO"  # Générée automatiquement par le système
    MANUEL = "MANUEL"  # Créée manuellement par un utilisateur

class TypeMaintenanceComplete(str, Enum):
    """
    Type de maintenance complet pour la TÂCHE 3.
    Étend le TypeMaintenanceEnum existant.
    """
    PREVENTIVE = "PREVENTIVE"  # Maintenance planifiée
    CORRECTIVE = "CORRECTIVE"  # Maintenance corrective
    PREDICTIVE = "PREDICTIVE"  # Maintenance prédictive basée sur l'IA
    CURATIVE = "CURATIVE"  # Maintenance curative (réparation)
    PREVENTIVE_AUTO = "PREVENTIVE_AUTO"  # Auto-générée par le système

class SeuilAlerteVNC(int, Enum):
    """
    Seuils d'alerte pour la Valeur Nette Comptable (TÂCHE 3).
    """
    CRITIQUE = 20  # 20% pour les biens critiques
    STANDARD = 5  # 5% pour les biens standards

class SeuilScoreFiabilite(int, Enum):
    """
    Seuils pour le score de fiabilité (TÂCHE 3).
    """
    CRITIQUE = 30  # En dessous de 30% → alerte rouge
    MOYEN = 60  # Entre 30% et 60% → alerte orange
    BON = 100  # Au-dessus de 60% → vert

class StatutAlerteVNC(str, Enum):
    """
    Statut des alertes VNC (TÂCHE 3).
    """
    EN_ATTENTE = "EN_ATTENTE"
    EN_COURS = "EN_COURS"
    TRAITEE = "TRAITEE"
    ANNULEE = "ANNULEE"

class StatutProjection(str, Enum):
    """
    Statut des projections d'investissement (TÂCHE 3).
    """
    ESTIMEE = "ESTIMEE"
    CONFIRMEE = "CONFIRMEE"
    REALISEE = "REALISEE"
    ANNULEE = "ANNULEE"