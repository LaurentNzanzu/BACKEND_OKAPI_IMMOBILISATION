# backend/app/api/endpoints/validations.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from datetime import datetime
import logging

from ...models.cession import Cession, StatutCession
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.validation import OrdreValidation, TypeValidation, Validation
from ...schemas.validation import (
    ValidationApprove, ValidationReject, ValidationDecision,
    ValidationResponse, ValidationDetailResponse, 
    ValidationListResponse, ValidationWorkflowStatus
)
from ...services.validation_service import ValidationService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/validations", tags=["Validations"])


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def check_validation_permission(user: Utilisateur, action: str = "view") -> bool:
    """Vérifie les permissions sur les validations."""
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]:
        return True
    if role in ["COMPTABLE", "CAISSE"] and action in ["view", "validate"]:
        return True
    return False


def get_user_ordre_validation(user: Utilisateur) -> str:
    """Récupère l'ordre de validation de l'utilisateur."""
    role = user.role.nom.upper() if user.role else "USER"
    if role == "COMPTABLE":
        return "COMPTABLE"
    elif role == "CAISSE":
        return "CAISSE"
    elif role == "DG":
        return "DG"
    return None


def _get_ordre_validation_from_role(user: Utilisateur) -> Optional[OrdreValidation]:
    """
    Mappe le rôle utilisateur vers l'ordre de validation.
    ✅ Utilisé dans les endpoints avec transaction
    """
    role = user.role.nom.upper() if user.role else "USER"
    mapping = {
        "COMPTABLE": OrdreValidation.COMPTABLE,
        "CAISSE": OrdreValidation.CAISSE,
        "DG": OrdreValidation.DG,
    }
    return mapping.get(role)


# ============================================================
# ENDPOINTS DE LECTURE
# ============================================================

@router.get("/en-attente", response_model=List[dict])
async def get_validations_en_attente(
    type_validation: Optional[TypeValidation] = Query(None, description="Type de validation"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les validations en attente pour l'utilisateur connecté.
    """
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    role = get_user_ordre_validation(current_user)
    
    if not role:
        return []
    
    return service.get_besoins_en_attente(role)


@router.get("/{besoin_id}/workflow", response_model=ValidationWorkflowStatus)
async def get_workflow_validation(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère le statut du workflow de validation d'un besoin."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    return service.get_workflow_details(besoin_id)


@router.get("/historique/{besoin_id}", response_model=List[dict])
async def get_historique_validations(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère l'historique des validations d'un besoin."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    return service.get_historique_validations(besoin_id)


@router.get("/types", response_model=List[str])
async def get_types_validation(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les types de validation disponibles."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    return [t.value for t in TypeValidation]


@router.get("/ordres", response_model=List[str])
async def get_ordres_validation(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les ordres de validation disponibles."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    return [o.value for o in OrdreValidation]


# ============================================================
# ENDPOINTS D'APPROBATION ET REJET (AVEC TRANSACTIONS ACID)
# ============================================================

@router.post("/{validation_id}/approuver", response_model=dict)
async def approuver_validation(
    validation_id: int,
    data: ValidationApprove,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Approuve une validation.
    Le rôle de l'utilisateur détermine l'étape du workflow.
    
    ✅ TRANSACTION ACID avec with db.begin()
    ✅ Le service ne fait PAS de commit isolé
    """
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        # Récupérer la validation avec verrou
        validation = db.query(Validation).filter(
            Validation.id_validation == validation_id
        ).with_for_update().first()
        
        if not validation:
            raise HTTPException(status_code=404, detail="Validation non trouvée")
        
        # Déterminer le type d'objet à valider
        if validation.type_validation == TypeValidation.BESOIN and validation.id_besoin:
            # 🔐 TRANSACTION UNIQUE via le service
            # Le service utilise with db.begin() à l'intérieur
            result = service.valider_besoin(
                besoin_id=validation.id_besoin,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="APPROUVE",
                commentaire=data.commentaire,
                piece_justificative_url=data.piece_justificative_url
            )
            
            # ✅ Audit - SUPPRESSION de request=request
            audit_service.log_action(
                user_id=current_user.id,
                table_name="validations",
                record_id=validation_id,
                action="APPROUVE",
                nouvelles_valeurs={
                    "besoin_id": validation.id_besoin,
                    "ordre": ordre,
                    "commentaire": data.commentaire
                }
            )
            
        elif validation.type_validation == TypeValidation.CESSION and validation.id_bien:
            # Récupérer la cession associée avec verrou
            cession = db.query(Cession).filter(
                Cession.id_bien == validation.id_bien,
                Cession.statut == StatutCession.EN_ATTENTE_VALIDATION
            ).with_for_update().first()
            
            if not cession:
                raise HTTPException(status_code=404, detail="Cession non trouvée")
            
            result = service.valider_cession(
                cession_id=cession.id_cession,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="APPROUVE",
                commentaire=data.commentaire,
                piece_justificative_url=data.piece_justificative_url
            )
            
            # ✅ Audit - SUPPRESSION de request=request
            audit_service.log_action(
                user_id=current_user.id,
                table_name="cessions",
                record_id=cession.id_cession,
                action="APPROUVE",
                nouvelles_valeurs={
                    "bien_id": validation.id_bien,
                    "ordre": ordre,
                    "statut": cession.statut.value if cession.statut else None
                }
            )
            
        else:
            raise HTTPException(status_code=400, detail="Type de validation non supporté")
        
        return {
            "success": True,
            "message": "Validation approuvée avec succès",
            "result": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD approbation validation {validation_id}: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


@router.post("/{validation_id}/rejeter", response_model=dict)
async def rejeter_validation(
    validation_id: int,
    data: ValidationReject,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Rejette une validation.
    Le motif de rejet est obligatoire.
    
    ✅ TRANSACTION ACID avec with db.begin()
    ✅ Le service ne fait PAS de commit isolé
    ✅ Libération du budget si déjà engagé
    """
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        # Récupérer la validation avec verrou
        validation = db.query(Validation).filter(
            Validation.id_validation == validation_id
        ).with_for_update().first()
        
        if not validation:
            raise HTTPException(status_code=404, detail="Validation non trouvée")
        
        # Déterminer le type d'objet à valider
        if validation.type_validation == TypeValidation.BESOIN and validation.id_besoin:
            result = service.valider_besoin(
                besoin_id=validation.id_besoin,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="REJETE",
                commentaire=data.motif_rejet,
                piece_justificative_url=data.piece_justificative_url
            )
            
            # ✅ Audit - SUPPRESSION de request=request
            audit_service.log_action(
                user_id=current_user.id,
                table_name="validations",
                record_id=validation_id,
                action="REJETE",
                nouvelles_valeurs={
                    "besoin_id": validation.id_besoin,
                    "ordre": ordre,
                    "motif": data.motif_rejet
                }
            )
            
        elif validation.type_validation == TypeValidation.CESSION and validation.id_bien:
            cession = db.query(Cession).filter(
                Cession.id_bien == validation.id_bien,
                Cession.statut == StatutCession.EN_ATTENTE_VALIDATION
            ).with_for_update().first()
            
            if not cession:
                raise HTTPException(status_code=404, detail="Cession non trouvée")
            
            result = service.valider_cession(
                cession_id=cession.id_cession,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="REJETE",
                commentaire=data.motif_rejet,
                piece_justificative_url=data.piece_justificative_url
            )
            
            # ✅ Audit - SUPPRESSION de request=request
            audit_service.log_action(
                user_id=current_user.id,
                table_name="cessions",
                record_id=cession.id_cession,
                action="REJETE",
                nouvelles_valeurs={
                    "bien_id": validation.id_bien,
                    "ordre": ordre,
                    "motif": data.motif_rejet
                }
            )
            
        else:
            raise HTTPException(status_code=400, detail="Type de validation non supporté")
        
        return {
            "success": True,
            "message": "Validation rejetée",
            "result": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD rejet validation {validation_id}: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


# ============================================================
# ENDPOINTS D'APPROBATION PAR BESOIN_ID
# ============================================================

@router.post("/besoin/{besoin_id}/approuver", response_model=dict)
async def approuver_besoin(
    besoin_id: int,
    data: ValidationApprove,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Approuve un besoin directement par son ID.
    Le rôle de l'utilisateur détermine l'étape du workflow.
    """
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        # Vérifier que le besoin existe
        from ...models.besoin import Besoin
        besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            raise HTTPException(status_code=404, detail="Besoin non trouvé")
        
        result = service.valider_besoin(
            besoin_id=besoin_id,
            id_validateur=current_user.id,
            ordre_validateur=ordre,
            decision="APPROUVE",
            commentaire=data.commentaire,
            piece_justificative_url=data.piece_justificative_url
        )
        
        # ✅ Audit - SUPPRESSION de request=request
        audit_service.log_action(
            user_id=current_user.id,
            table_name="besoins",
            record_id=besoin_id,
            action="APPROUVE",
            nouvelles_valeurs={
                "besoin_id": besoin_id,
                "ordre": ordre,
                "commentaire": data.commentaire
            }
        )
        
        return {
            "success": True,
            "message": "Besoin approuvé avec succès",
            "result": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD approbation besoin {besoin_id}: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


@router.post("/besoin/{besoin_id}/rejeter", response_model=dict)
async def rejeter_besoin(
    besoin_id: int,
    data: ValidationReject,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Rejette un besoin directement par son ID.
    Le motif de rejet est obligatoire.
    """
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        # Vérifier que le besoin existe
        from ...models.besoin import Besoin
        besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            raise HTTPException(status_code=404, detail="Besoin non trouvé")
        
        result = service.valider_besoin(
            besoin_id=besoin_id,
            id_validateur=current_user.id,
            ordre_validateur=ordre,
            decision="REJETE",
            commentaire=data.motif_rejet,
            piece_justificative_url=data.piece_justificative_url
        )
        
        # ✅ Audit - SUPPRESSION de request=request
        audit_service.log_action(
            user_id=current_user.id,
            table_name="besoins",
            record_id=besoin_id,
            action="REJETE",
            nouvelles_valeurs={
                "besoin_id": besoin_id,
                "ordre": ordre,
                "motif": data.motif_rejet
            }
        )
        
        return {
            "success": True,
            "message": "Besoin rejeté",
            "result": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD rejet besoin {besoin_id}: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


# ============================================================
# ENDPOINTS POUR AMORTISSEMENTS ET CESSIONS EN ATTENTE
# ============================================================

@router.get("/amortissements", response_model=List[dict])
async def get_amortissements_a_valider(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les amortissements en attente de validation.
    """
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    return service.get_amortissements_en_attente()


@router.get("/cessions", response_model=List[dict])
async def get_cessions_a_valider(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les cessions en attente de validation.
    """
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    return service.get_cessions_en_attente()