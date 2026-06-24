from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class TypeNotificationEnum(str, Enum):
    BESOIN_CREE = "BESOIN_CREE"
    BESOIN_VALIDE = "BESOIN_VALIDE"
    BESOIN_REJETE = "BESOIN_REJETE"
    MAINTENANCE_PLANIFIEE = "MAINTENANCE_PLANIFIEE"
    ALERTE_STOCK = "ALERTE_STOCK"
    ALERTE_FIN_ECHANCE_MAINTENANCE = "ALERTE_FIN_ECHANCE_MAINTENANCE"
    ALERTE_VNC_ZERO = "ALERTE_VNC_ZERO"
    RAPPEL_AMORTISSEMENT_MANQUANT = "RAPPEL_AMORTISSEMENT_MANQUANT"
    DECISION_IA_HEALTH_SCORE = "DECISION_IA_HEALTH_SCORE"
    DECISION_IA_STRATEGIQUE = "DECISION_IA_STRATEGIQUE"
    DECISION_IA_ACHAT = "DECISION_IA_ACHAT"
    MOUVEMENT_CREE = "MOUVEMENT_CREE"
    AMORTISSEMENT_CALCULE = "AMORTISSEMENT_CALCULE"
    FOURNITURE_EN_ATTENTE = "FOURNITURE_EN_ATTENTE"
    FOURNITURE_VALIDEE = "FOURNITURE_VALIDEE"
    STOCK_INSUFFISANT = "STOCK_INSUFFISANT"
    BIEN_EN_TEST = "BIEN_EN_TEST"
    PANNE_RESOLUE = "PANNE_RESOLUE"

class PrioriteNotificationEnum(str, Enum):
    information = "information"
    importante = "importante"
    critique = "critique"

class NotificationResponse(BaseModel):
    id_notification: int
    type_notification: TypeNotificationEnum
    titre: str
    contenu: str
    lien_action: Optional[str] = None
    date_creation: datetime
    priorite: PrioriteNotificationEnum = PrioriteNotificationEnum.information
    est_lu: bool = False
    est_archivee: bool = False

    @property
    def id(self) -> int:
        """Compatibilité frontend"""
        return self.id_notification

    model_config = ConfigDict(from_attributes=True)

class NotificationUpdate(BaseModel):
    est_lu: bool = True

class NotificationListParams(BaseModel):
    """Documentation des paramètres GET /notifications/"""
    limit: int = Field(50, ge=1, le=200)
    est_lu: Optional[bool] = Field(None, description="True=lues, False=non lues")
    priorite: Optional[PrioriteNotificationEnum] = Field(None, description="information | importante | critique")
    include_archivees: bool = Field(False, description="Inclure les notifications archivées par l'utilisateur")
