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
from ...services.workflow_service import WorkflowService

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
    role = user.role.nom.upper() if user.role else "USER"
    mapping = {
        "COMPTABLE": OrdreValidation.COMPTABLE,
        "CAISSE": OrdreValidation.CAISSE,
        "DG": OrdreValidation.DG,
    }
    return mapping.get(role)


def _get_prochain_validateur_dynamique_endpoint(
    db: Session,
    type_workflow: str,
    etape_actuelle: str,
    organisation_id: Optional[int],
    contexte: Optional[dict] = None,
) -> Optional[str]:
    """Retourne le rôle du prochain validateur selon le workflow configuré par l'ONG."""
    if organisation_id and etape_actuelle:
        try:
            ws = WorkflowService(db)
            etapes = ws.obtenir_etapes(
                type_workflow=type_workflow,
                organisation_id=organisation_id,
            )
            ordre_actuel = None
            for e in etapes:
                if e.role_requis and e.role_requis.upper() == etape_actuelle.upper():
                    ordre_actuel = e.ordre
                    break
            if ordre_actuel is not None:
                prochaine = ws.prochaine_etape(
                    type_workflow=type_workflow,
                    ordre_actuel=ordre_actuel,
                    organisation_id=organisation_id,
                    contexte=contexte or {},
                )
                if prochaine:
                    return prochaine.role_requis
                return None
        except Exception as e:
            logger.warning(
                f"[workflow] Erreur dynamique sur {type_workflow}/"
                f"org#{organisation_id}/etape={etape_actuelle} : {e}"
            )
    legacy = {"COMPTABLE": "CAISSE", "CAISSE": "DG", "DG": None}
    return legacy.get((etape_actuelle or "").upper())


# ═══ AJOUT 5.12.d — Helpers de vérification multi-tenant ═══
def _check_organisation_access(
    current_user: Utilisateur,
    organisation_id_resource: Optional[int],
    resource_label: str = "ressource",
) -> None:
    """
    Vérifie l'isolation multi-tenant.
    - ADMIN plateforme (is_platform_admin=True) → accès total autorisé
    - Sinon : la ressource doit appartenir à la même ONG
    - Ressource sans organisation_id → accès refusé (donnée legacy/historique)

    Lève HTTPException 403 si l'accès est interdit.
    """
    if getattr(current_user, "is_platform_admin", False):
        return

    if organisation_id_resource is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Accès refusé : {resource_label} sans organisation "
                f"(donnée historique). Contactez l'administrateur plateforme."
            ),
        )

    if organisation_id_resource != getattr(current_user, "organisation_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accès refusé : {resource_label} appartient à une autre organisation.",
        )


def _check_acces_besoin(db: Session, current_user: Utilisateur, besoin) -> None:
    """Vérifie l'accès à un Besoin. Lève 403 si interdit."""
    svc = ValidationService(db)
    org_id = svc._get_organisation_id_besoin(besoin)
    _check_organisation_access(current_user, org_id, f"besoin #{getattr(besoin, 'id_besoin', '?')}")


def _check_acces_validation(db: Session, current_user: Utilisateur, validation) -> None:
    """Vérifie l'accès à une Validation. Lève 403 si interdit."""
    svc = ValidationService(db)
    org_id = svc.get_organisation_id_validation(validation)
    _check_organisation_access(current_user, org_id, f"validation #{getattr(validation, 'id_validation', '?')}")


def _check_acces_cession(db: Session, current_user: Utilisateur, cession) -> None:
    """Vérifie l'accès à une Cession. Lève 403 si interdit."""
    svc = ValidationService(db)
    org_id = svc.get_organisation_id_cession(cession)
    _check_organisation_access(current_user, org_id, f"cession #{getattr(cession, 'id_cession', '?')}")
# ═══ FIN AJOUT 5.12.d ═══


# ============================================================
# ENDPOINTS DE LECTURE
# ============================================================

@router.get("/en-attente", response_model=List[dict])
async def get_validations_en_attente(
    type_validation: Optional[TypeValidation] = Query(None, description="Type de validation"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les validations en attente pour l'utilisateur connecté."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    role = get_user_ordre_validation(current_user)
    
    if not role:
        return []
    
    # ═══ MODIF 5.12.d — Filtre multi-tenant ═══
    if getattr(current_user, "is_platform_admin", False):
        return service.get_besoins_en_attente(role, organisation_id=None, is_platform_admin=True)
    return service.get_besoins_en_attente(
        role,
        organisation_id=current_user.organisation_id,
        is_platform_admin=False,
    )


@router.get("/{besoin_id}/workflow", response_model=ValidationWorkflowStatus)
async def get_workflow_validation(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère le statut du workflow de validation d'un besoin."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.12.d — Vérification d'accès ═══
    from ...models.besoin import Besoin
    besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
    if not besoin:
        raise HTTPException(status_code=404, detail="Besoin non trouvé")
    _check_acces_besoin(db, current_user, besoin)

    service = ValidationService(db)
    return service.get_workflow_details(besoin_id)


@router.get("/workflow-dynamique/{besoin_id}")
async def get_workflow_dynamique_besoin(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Retourne l'étape actuelle et le prochain validateur d'un besoin."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    from ...models.besoin import Besoin

    besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
    if not besoin:
        raise HTTPException(status_code=404, detail="Besoin non trouvé")

    # ═══ MODIF 5.12.d — Vérification d'accès ═══
    _check_acces_besoin(db, current_user, besoin)

    service = ValidationService(db)
    etape_actuelle = service._get_etape_actuelle(besoin)
    organisation_id = service._get_organisation_id_besoin(besoin)

    if etape_actuelle in ("TERMINE", "REJETE", None):
        prochain = None
    else:
        prochain = _get_prochain_validateur_dynamique_endpoint(
            db=db,
            type_workflow="BESOIN",
            etape_actuelle=etape_actuelle,
            organisation_id=organisation_id,
            contexte={"montant_total": float(besoin.montant_total or 0)},
        )

    return {
        "id_besoin": besoin.id_besoin,
        "numero_demande": besoin.numero_demande,
        "statut": besoin.statut.value if besoin.statut else None,
        "montant_total": float(besoin.montant_total or 0),
        "etape_actuelle": etape_actuelle,
        "prochain_validateur": prochain,
        "organisation_id": organisation_id,
        "workflow_source": "DYNAMIQUE" if organisation_id else "LEGACY",
    }


@router.get("/historique/{besoin_id}", response_model=List[dict])
async def get_historique_validations(
    besoin_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère l'historique des validations d'un besoin."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ MODIF 5.12.d — Vérification d'accès ═══
    from ...models.besoin import Besoin
    besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
    if not besoin:
        raise HTTPException(status_code=404, detail="Besoin non trouvé")
    _check_acces_besoin(db, current_user, besoin)

    service = ValidationService(db)
    return service.get_historique_validations(besoin_id)


@router.get("/types", response_model=List[str])
async def get_types_validation(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    return [t.value for t in TypeValidation]


@router.get("/ordres", response_model=List[str])
async def get_ordres_validation(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    return [o.value for o in OrdreValidation]


# ============================================================
# ENDPOINTS D'APPROBATION ET REJET
# ============================================================

@router.post("/{validation_id}/approuver", response_model=dict)
async def approuver_validation(
    validation_id: int,
    data: ValidationApprove,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Approuve une validation."""
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        validation = db.query(Validation).filter(
            Validation.id_validation == validation_id
        ).with_for_update().first()
        
        if not validation:
            raise HTTPException(status_code=404, detail="Validation non trouvée")

        # ═══ MODIF 5.12.d — Vérification d'accès ═══
        _check_acces_validation(db, current_user, validation)

        if validation.type_validation == TypeValidation.BESOIN and validation.id_besoin:
            result = service.valider_besoin(
                besoin_id=validation.id_besoin,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="APPROUVE",
                commentaire=data.commentaire,
                piece_justificative_url=data.piece_justificative_url
            )
            
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
            cession = db.query(Cession).filter(
                Cession.id_bien == validation.id_bien,
                Cession.statut == StatutCession.EN_ATTENTE_VALIDATION
            ).with_for_update().first()
            
            if not cession:
                raise HTTPException(status_code=404, detail="Cession non trouvée")

            # ═══ MODIF 5.12.d — Vérification d'accès sur la cession ═══
            _check_acces_cession(db, current_user, cession)

            result = service.valider_cession(
                cession_id=cession.id_cession,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="APPROUVE",
                commentaire=data.commentaire,
                piece_justificative_url=data.piece_justificative_url
            )
            
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
        
    except HTTPException:
        raise
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
    """Rejette une validation."""
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        validation = db.query(Validation).filter(
            Validation.id_validation == validation_id
        ).with_for_update().first()
        
        if not validation:
            raise HTTPException(status_code=404, detail="Validation non trouvée")

        # ═══ MODIF 5.12.d — Vérification d'accès ═══
        _check_acces_validation(db, current_user, validation)

        if validation.type_validation == TypeValidation.BESOIN and validation.id_besoin:
            result = service.valider_besoin(
                besoin_id=validation.id_besoin,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="REJETE",
                commentaire=data.motif_rejet,
                piece_justificative_url=data.piece_justificative_url
            )
            
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

            # ═══ MODIF 5.12.d — Vérification d'accès sur la cession ═══
            _check_acces_cession(db, current_user, cession)

            result = service.valider_cession(
                cession_id=cession.id_cession,
                id_validateur=current_user.id,
                ordre_validateur=ordre,
                decision="REJETE",
                commentaire=data.motif_rejet,
                piece_justificative_url=data.piece_justificative_url
            )
            
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
        
    except HTTPException:
        raise
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
    """Approuve un besoin directement par son ID."""
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        from ...models.besoin import Besoin
        besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            raise HTTPException(status_code=404, detail="Besoin non trouvé")

        # ═══ MODIF 5.12.d — Vérification d'accès ═══
        _check_acces_besoin(db, current_user, besoin)

        result = service.valider_besoin(
            besoin_id=besoin_id,
            id_validateur=current_user.id,
            ordre_validateur=ordre,
            decision="APPROUVE",
            commentaire=data.commentaire,
            piece_justificative_url=data.piece_justificative_url
        )
        
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
        
    except HTTPException:
        raise
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
    """Rejette un besoin directement par son ID."""
    if not check_validation_permission(current_user, "validate"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    ordre = get_user_ordre_validation(current_user)
    if not ordre:
        raise HTTPException(status_code=400, detail="Rôle non valide pour la validation")
    
    service = ValidationService(db)
    audit_service = AuditService(db)
    
    try:
        from ...models.besoin import Besoin
        besoin = db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            raise HTTPException(status_code=404, detail="Besoin non trouvé")

        # ═══ MODIF 5.12.d — Vérification d'accès ═══
        _check_acces_besoin(db, current_user, besoin)

        result = service.valider_besoin(
            besoin_id=besoin_id,
            id_validateur=current_user.id,
            ordre_validateur=ordre,
            decision="REJETE",
            commentaire=data.motif_rejet,
            piece_justificative_url=data.piece_justificative_url
        )
        
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
        
    except HTTPException:
        raise
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
    """Récupère les amortissements en attente de validation."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    # ═══ MODIF 5.12.d — Filtre multi-tenant ═══
    if getattr(current_user, "is_platform_admin", False):
        return service.get_amortissements_en_attente(organisation_id=None, is_platform_admin=True)
    return service.get_amortissements_en_attente(
        organisation_id=current_user.organisation_id,
        is_platform_admin=False,
    )


@router.get("/cessions", response_model=List[dict])
async def get_cessions_a_valider(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les cessions en attente de validation."""
    if not check_validation_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ValidationService(db)
    # ═══ MODIF 5.12.d — Filtre multi-tenant ═══
    if getattr(current_user, "is_platform_admin", False):
        return service.get_cessions_en_attente(organisation_id=None, is_platform_admin=True)
    return service.get_cessions_en_attente(
        organisation_id=current_user.organisation_id,
        is_platform_admin=False,
    )