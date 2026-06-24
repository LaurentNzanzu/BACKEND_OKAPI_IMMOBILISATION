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