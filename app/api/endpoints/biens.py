# backend/app/api/endpoints/biens.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from fastapi.responses import StreamingResponse
import io
from typing import List, Optional
import logging
from pydantic import ValidationError

from ...models.validation import DecisionValidation, OrdreValidation, TypeValidation, Validation
from ...schemas.notification import TypeNotificationEnum
from ...services.notification_service import NotificationService
from ...services.validation_service import ValidationService

from ...core.database import get_db
from ...core.bien_permissions import (
    can_view_biens,
    can_view_financial_data,
    can_create_bien,
    can_delete_bien,
    can_update_bien,
    can_view_bien_detail,
    get_user_role,
    filter_bien_update,
    sanitize_bien_dict,
    log_access_denied,
    log_access_granted,
)
from ...schemas.bien import BienCreate, BienUpdate, BienResponse, BienListResponse, LocalisationBrief
from ...schemas.fournisseur import FournisseurResponse
from ...services.bien_service import BienService
from ...services.fournisseur_service import FournisseurService
from ...services.comptabilite_service import ComptabiliteService
from ...services.qr_code_service import QRCodeService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien, EtatBien
from ...models.maintenance import Maintenance, StatutMaintenance, TypeOrigineMaintenance
from ...models.ordre_remplacement import OrdreRemplacement, StatutOrdreRemplacement
from ...schemas.cession import (
    CessionCreate, CessionUpdate, CessionResponse, 
    CessionEligibilityResponse, CessionValidationWorkflow
)
from ...models.cession import Cession, StatutCession
from ...services.comptabilite_service import ComptabiliteService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/biens", tags=["Biens"])


def _to_bien_response(bien, user: Utilisateur) -> BienResponse:
    resp_obj = BienResponse.model_validate(bien)
    if getattr(bien, "localisation_ref", None) and not resp_obj.localisation:
        resp_obj.localisation = bien.localisation_ref
    obj_dict = resp_obj.model_dump()
    sanitized = sanitize_bien_dict(obj_dict, user)
    return BienResponse.model_validate(sanitized)


def _deny(user: Utilisateur, action: str, detail: str, request: Request = None, resource_id: int = None):
    log_access_denied(user, action, detail=detail, request=request, resource_id=resource_id)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# ============================================================
# FONCTION ASYNCHRONE POUR LE CALCUL DU SCORE (BACKGROUND TASK)
# ============================================================

def _calculer_score_async(bien_id: int):
    """
    Fonction exécutée en arrière-plan pour le calcul du score de fiabilité.
    Crée sa propre session pour isolation.
    """
    from ...core.database import SessionLocal
    from ...services.maintenance_service import MaintenanceService
    
    db = SessionLocal()
    try:
        service = MaintenanceService(db)
        service.calculer_score_fiabilite(bien_id)
        logger.info(f"✅ Score recalculé avec succès pour bien {bien_id}")
    except Exception as e:
        logger.error(f"❌ Erreur calcul score bien {bien_id}: {e}")
    finally:
        db.close()


# ============================================================
# ENDPOINTS CRUD
# ============================================================

@router.post("/", response_model=BienResponse, status_code=status.HTTP_201_CREATED)
async def create_bien(
    bien_data: BienCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_create_bien(current_user):
        _deny(current_user, "create_bien", "Permissions insuffisantes pour créer un bien", request)

    if bien_data.mode_paiement == "credit" and bien_data.fournisseur_id:
        fournisseur = FournisseurService(db).get_by_id(bien_data.fournisseur_id)
        if not fournisseur:
            raise HTTPException(status_code=404, detail="Fournisseur non trouvé")

    service = BienService(db)
    
    try:
        bien = service.create_bien(bien_data)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création bien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    audit_service.log_create(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien.id_bien,
        new_values={
            "type_bien": bien.type_bien,
            "marque": getattr(bien, "marque", getattr(bien, "fabricant", None)),
            "modele": getattr(bien, "modele", None),
            "prix_acquisition": float(bien.prix_acquisition) if bien.prix_acquisition else None,
            "mode_paiement": bien.mode_paiement,
            "qr_code": bien.qr_code,
        },
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.get("", response_model=BienListResponse)
@router.get("/", response_model=BienListResponse, include_in_schema=False)
def get_biens(
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=1000),
    type_bien: Optional[str] = None,
    etat: Optional[str] = None,
    search: Optional[str] = Query(None, description="Recherche par désignation"),
    disponible_maintenance: bool = Query(False, description="Filtrer pour n'avoir que les biens disponibles pour la maintenance"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not can_view_biens(current_user):
        _deny(current_user, "list_biens", "Permissions insuffisantes pour voir les biens", request)

    service = BienService(db)
    etat_enum = None
    if etat:
        try:
            etat_enum = EtatBien(etat.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"État invalide. Valeurs possibles: {[e.value for e in EtatBien]}",
            )

    try:
        if get_user_role(current_user) == "TECHNICIEN":
            biens = service.get_biens_for_technicien(
                current_user.id,
                skip=skip,
                limit=limit,
                type_bien=type_bien,
                etat=etat_enum,
                search=search,
                disponible_maintenance=disponible_maintenance,
            )
        else:
            biens = service.get_all_biens(
                skip=skip,
                limit=limit,
                type_bien=type_bien,
                etat=etat_enum,
                search=search,
                disponible_maintenance=disponible_maintenance,
            )

        total_count = service.get_biens_count(
            type_bien=type_bien,
            etat=etat_enum,
            search=search,
            disponible_maintenance=disponible_maintenance,
        )

        return BienListResponse(
            total=total_count,
            page=(skip // limit) + 1,
            page_size=limit,
            biens=[_to_bien_response(b, current_user) for b in biens],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des biens: {str(e)}", exc_info=True)
        if isinstance(e, ValidationError):
            logger.error(f"Détails de l'erreur de validation Pydantic : {e.errors()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur de validation de schéma (Pydantic): {e.errors()}"
            )
        if isinstance(e, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne: {str(e)}"
        )


@router.get("/{bien_id}", response_model=BienResponse)
async def get_bien(
    bien_id: int,
    panne_id: Optional[int] = Query(None, description="Contexte panne pour accès technicien"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not can_view_biens(current_user):
        _deny(current_user, "view_bien", "Permissions insuffisantes pour voir ce bien", request, bien_id)

    service = BienService(db)
    try:
        bien = service.get_bien_by_id(bien_id)
        if not bien:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

        if not can_view_bien_detail(current_user, bien, db, panne_id):
            _deny(
                current_user,
                "view_bien_detail",
                "Accès refusé : ce bien n'est pas dans votre périmètre technicien",
                request,
                bien_id,
            )

        log_access_granted(
            current_user,
            "view_bien_detail",
            resource_id=bien_id,
            detail=f"panne_id={panne_id}" if panne_id else None,
            request=request,
        )

        return _to_bien_response(bien, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du bien: {str(e)}", exc_info=True)
        if isinstance(e, ValidationError):
            logger.error(f"Détails de l'erreur de validation Pydantic : {e.errors()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur de validation de schéma (Pydantic): {e.errors()}"
            )
        if isinstance(e, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne: {str(e)}"
        )


@router.put("/{bien_id}", response_model=BienResponse)
async def update_bien(
    bien_id: int,
    bien_data: BienUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_update_bien(current_user):
        _deny(
            current_user,
            "update_bien",
            "Permissions insuffisantes pour modifier un bien",
            request,
            bien_id,
        )

    service = BienService(db)
    old_bien = service.get_bien_by_id(bien_id)
    if not old_bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    filtered_data = filter_bien_update(current_user, bien_data)
    if not filtered_data.model_dump(exclude_unset=True):
        _deny(
            current_user,
            "update_bien_empty",
            "Aucun champ modifiable autorisé pour votre rôle",
            request,
            bien_id,
        )

    try:
        bien = service.update_bien(bien_id, filtered_data)
    except HTTPException:
        raise
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    old_values = {
        "etat": old_bien.etat.value if old_bien.etat else None,
        "id_localisation": old_bien.id_localisation,
        "description": old_bien.description,
    }
    new_values = {
        "etat": bien.etat.value if bien.etat else None,
        "id_localisation": bien.id_localisation,
        "description": bien.description,
    }
    if can_view_financial_data(current_user):
        old_values["prix_acquisition"] = float(old_bien.prix_acquisition) if old_bien.prix_acquisition else None
        new_values["prix_acquisition"] = float(bien.prix_acquisition) if bien.prix_acquisition else None

    audit_service.log_update(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien_id,
        old_values=old_values,
        new_values=new_values,
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.delete("/{bien_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bien(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_delete_bien(current_user):
        _deny(
            current_user,
            "delete_bien",
            "Permissions insuffisantes pour supprimer un bien",
            request,
            bien_id,
        )

    service = BienService(db)
    bien = service.get_bien_by_id(bien_id)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    audit_service.log_delete(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien_id,
        old_values={
            "type_bien": bien.type_bien,
            "marque": getattr(bien, "marque", getattr(bien, "fabricant", None)),
            "modele": getattr(bien, "modele", None),
            "qr_code": bien.qr_code,
        },
        request=request,
    )

    if not service.delete_bien(bien_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")


@router.get("/{bien_id}/qr-code")
async def get_bien_qr_code(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not can_view_biens(current_user):
        _deny(current_user, "view_qr", "Permissions insuffisantes", resource_id=bien_id)

    service = BienService(db)
    bien = service.get_bien_by_id(bien_id)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    qr_service = QRCodeService()
    qr_code_image = qr_service.generate_qr_code(bien.qr_code, bien_id)

    return StreamingResponse(
        io.BytesIO(qr_code_image),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_code_{bien_id}.png"},
    )


@router.get("/{bien_id}/age")
async def get_bien_age(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not can_view_biens(current_user):
        _deny(current_user, "view_bien_age", "Permissions insuffisantes", resource_id=bien_id)

    service = BienService(db)
    age = service.calculer_age_bien(bien_id)
    if age is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    return {"bien_id": bien_id, "age_years": age}


@router.patch("/{bien_id}/etat")
async def change_bien_etat(
    bien_id: int,
    nouvel_etat: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_update_bien(current_user):
        _deny(
            current_user,
            "change_etat",
            "Permissions insuffisantes pour modifier l'état d'un bien",
            request,
            bien_id,
        )

    service = BienService(db)
    old_bien = service.get_bien_by_id(bien_id)
    if not old_bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    try:
        etat = EtatBien(nouvel_etat)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"État invalide. Valeurs possibles: {[e.value for e in EtatBien]}",
        )

    bien = service.changer_etat_bien(bien_id, etat)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    audit_service.log_update(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien_id,
        old_values={"etat": old_bien.etat.value if old_bien.etat else None},
        new_values={"etat": nouvel_etat},
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.get("/statistics/summary")
async def get_biens_statistics(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not can_view_biens(current_user):
        _deny(current_user, "biens_statistics", "Permissions insuffisantes")

    service = BienService(db)
    stats = service.get_statistics()

    if not can_view_financial_data(current_user):
        stats.pop("valeur_totale", None)

    return stats


# ============================================================
# ENDPOINTS DE CESSION (TÂCHE 2)
# ============================================================

@router.get("/{bien_id}/cession/eligibilite", response_model=CessionEligibilityResponse)
async def verifier_eligibilite_cession(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Vérifie si un bien est éligible à la cession selon les 4 règles.
    Règles: Garantie, État, Amortissement, Pannes consécutives.
    """
    if not can_view_biens(current_user):
        _deny(current_user, "check_cession", "Permissions insuffisantes", request, bien_id)
    
    service = BienService(db)
    bien = service.get_bien_by_id(bien_id)
    if not bien:
        raise HTTPException(status_code=404, detail=f"Bien {bien_id} non trouvé")
    
    try:
        return service.verifier_eligibilite_cession(bien_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/eligibles-cession", response_model=List[CessionEligibilityResponse])
def get_biens_eligibles_cession(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Récupère la liste des biens éligibles à la cession.
    """
    if not can_view_biens(current_user):
        _deny(current_user, "list_eligible_cession", "Permissions insuffisantes", request)
    
    from sqlalchemy.orm import selectinload
    biens = db.query(Bien).options(
        joinedload(Bien.localisation_ref),
        selectinload(Bien.amortissements),
        selectinload(Bien.pannes)
    ).all()
    
    service = BienService(db)
    resultats = []
    for bien in biens:
        try:
            eligibilite = service.verifier_eligibilite_cession_optimise(bien)
            if eligibilite["est_eligible"]:
                resultats.append(eligibilite)
        except Exception as e:
            logger.warning(f"Erreur vérification éligibilité bien {bien.id_bien}: {str(e)}")
    
    return resultats


@router.post("/{bien_id}/cession", response_model=CessionResponse, status_code=status.HTTP_201_CREATED)
async def demander_cession(
    bien_id: int,
    data: CessionCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Déclenche le workflow de cession pour un bien.
    Vérifie d'abord les 4 règles d'éligibilité.
    
    ✅ TRANSACTION ACID avec with db.begin()
    ✅ Verrou pessimiste sur le bien
    ✅ Création atomique : cession + validations
    """
    if not can_update_bien(current_user):
        _deny(current_user, "demander_cession", "Permissions insuffisantes pour demander une cession", request, bien_id)
    
    service = BienService(db)
    audit_service = AuditService(db)
    
    try:
        with db.begin():
            # 1. Vérifier que le bien existe (avec verrou)
            bien = service.get_bien_by_id(bien_id)
            if not bien:
                raise HTTPException(status_code=404, detail=f"Bien {bien_id} non trouvé")
            
            # 2. Vérifier l'éligibilité
            try:
                eligibilite = service.verifier_eligibilite_cession(bien_id)
                if not eligibilite["est_eligible"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Ce bien n'est pas éligible à la cession. Motifs: {', '.join(eligibilite['motifs_ineligibilite'])}"
                    )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            
            # 3. Vérifier que le bien n'est pas déjà en cession
            existing_cession = db.query(Cession).filter(
                Cession.id_bien == bien_id,
                Cession.statut.in_([StatutCession.EN_ATTENTE_VALIDATION, StatutCession.EN_COURS])
            ).first()
            if existing_cession:
                raise HTTPException(status_code=400, detail="Une demande de cession est déjà en cours pour ce bien")
            
            # 4. Vérifier le bien de remplacement
            if data.actif_remplacement_id:
                remplacement = service.get_bien_by_id(data.actif_remplacement_id)
                if not remplacement:
                    raise HTTPException(status_code=404, detail="Bien de remplacement non trouvé")
                if remplacement.id_bien == bien_id:
                    raise HTTPException(status_code=400, detail="Le bien de remplacement ne peut pas être le même que le bien cédé")
            
            # 5. Calculer la VNC
            vnc = bien.valeur_nette_comptable
            
            # 6. Créer la cession
            comptabilite = ComptabiliteService(db, cree_par_id=current_user.id)
            cession, ecritures = comptabilite.enregistrer_cession(data)
            
            # 7. Mettre à jour le statut de la cession
            cession.statut = StatutCession.EN_ATTENTE_VALIDATION
            cession.cree_par = current_user.id
            cession.valeur_nette_comptable = vnc
            
            # 8. Lier l'actif de remplacement
            if data.actif_remplacement_id:
                cession.actif_remplacement_id = data.actif_remplacement_id
            
            db.add(cession)
            db.flush()
            
            # 9. Créer les validations pour le workflow
            validation_service = ValidationService(db)
            
            # Validation Comptable
            validation_comptable = Validation(
                id_bien=bien_id,
                id_validateur=None,
                ordre_validateur=OrdreValidation.COMPTABLE,
                type_validation=TypeValidation.CESSION,
                decision=DecisionValidation.EN_ATTENTE,
                date_validation=datetime.utcnow()
            )
            db.add(validation_comptable)
            
            # Validation Caissier
            validation_caissier = Validation(
                id_bien=bien_id,
                id_validateur=None,
                ordre_validateur=OrdreValidation.CAISSE,
                type_validation=TypeValidation.CESSION,
                decision=DecisionValidation.EN_ATTENTE,
                date_validation=datetime.utcnow()
            )
            db.add(validation_caissier)
            
            # Validation DG
            validation_dg = Validation(
                id_bien=bien_id,
                id_validateur=None,
                ordre_validateur=OrdreValidation.DG,
                type_validation=TypeValidation.CESSION,
                decision=DecisionValidation.EN_ATTENTE,
                date_validation=datetime.utcnow()
            )
            db.add(validation_dg)
            
            # Le commit est automatique à la sortie du with
            
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD lors de la demande de cession: {str(e)}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la demande de cession: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")
    
    # Notifications hors transaction
    try:
        notification_service = NotificationService(db)
        comptables = validation_service._get_utilisateurs_par_roles("COMPTABLE")
        for comptable in comptables:
            notification_service.envoyer_notification(
                ids_destinataires=comptable.id,
                type_notif=TypeNotificationEnum.BESOIN_VALIDE,
                titre=f"📋 Demande de cession - Bien #{bien_id}",
                contenu=f"Une demande de cession a été soumise pour le bien #{bien_id}. Veuillez valider.",
                lien=f"/cessions/{cession.id_cession}"
            )
    except Exception as e:
        logger.warning(f"Erreur notification (non bloquante): {e}")
    
    # Audit
    audit_service.log_create(
        user_id=current_user.id,
        table_name="cessions",
        record_id=cession.id_cession,
        new_values={
            "id_bien": bien_id,
            "prix_vente": float(data.prix_vente),
            "vnc": float(vnc),
            "type_cession": data.type_cession,
            "actif_remplacement_id": data.actif_remplacement_id
        },
        request=request
    )
    
    return cession


@router.get("/{bien_id}/cession/workflow", response_model=CessionValidationWorkflow)
async def get_cession_workflow(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Récupère le statut du workflow de cession d'un bien."""
    if not can_view_biens(current_user):
        _deny(current_user, "view_cession_workflow", "Permissions insuffisantes", request, bien_id)
    
    cession = db.query(Cession).filter(
        Cession.id_bien == bien_id
    ).order_by(Cession.created_at.desc()).first()
    
    if not cession:
        raise HTTPException(status_code=404, detail="Aucune cession trouvée pour ce bien")
    
    validations = db.query(Validation).filter(
        Validation.id_bien == bien_id,
        Validation.type_validation == TypeValidation.CESSION
    ).all()
    
    etape_actuelle = "EN_ATTENTE"
    for v in validations:
        if v.decision == DecisionValidation.EN_ATTENTE:
            etape_actuelle = v.ordre_validateur.value
            break
    
    ordres = [OrdreValidation.COMPTABLE, OrdreValidation.CAISSE, OrdreValidation.DG]
    prochaine_etape = None
    for ordre in ordres:
        found = False
        for v in validations:
            if v.ordre_validateur == ordre:
                found = True
                break
        if not found:
            prochaine_etape = ordre.value
            break
    
    return CessionValidationWorkflow(
        id_bien=bien_id,
        id_cession=cession.id_cession,
        etape_actuelle=etape_actuelle,
        prochaine_etape=prochaine_etape,
        validation_comptable=next((v for v in validations if v.ordre_validateur == OrdreValidation.COMPTABLE), None),
        validation_caissier=next((v for v in validations if v.ordre_validateur == OrdreValidation.CAISSE), None),
        validation_dg=next((v for v in validations if v.ordre_validateur == OrdreValidation.DG), None),
        est_complete=cession.statut in [StatutCession.ACCORDEE, StatutCession.REJETEE],
        est_approuvee=cession.statut == StatutCession.ACCORDEE,
        statut_global=cession.statut
    )


# ============================================================
# NOUVEAUX ENDPOINTS TÂCHE 3 - SCORE DE FIABILITÉ (AVEC BACKGROUNDTASKS)
# ============================================================

@router.get("/{bien_id}/score-fiabilite")
async def get_score_fiabilite(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère le score de fiabilité d'un bien avec son historique.
    Lecture rapide, données pré-calculées.
    """
    if not can_view_biens(current_user):
        _deny(current_user, "view_score_fiabilite", "Permissions insuffisantes", resource_id=bien_id)

    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(404, "Bien non trouvé")
    
    from ...models.journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation
    
    historique_scores = db.query(JournalEvenementImmobilisation).filter(
        JournalEvenementImmobilisation.bien_id == bien_id,
        JournalEvenementImmobilisation.type_evenement == TypeEvenementImmobilisation.SCORE_FIABILITE
    ).order_by(JournalEvenementImmobilisation.date_evenement.desc()).limit(12).all()
    
    maintenances_auto = db.query(Maintenance).filter(
        Maintenance.id_bien == bien_id,
        Maintenance.origine == TypeOrigineMaintenance.AUTO
    ).order_by(Maintenance.date_creation.desc()).limit(5).all()
    
    ordres = db.query(OrdreRemplacement).filter(
        OrdreRemplacement.bien_id == bien_id
    ).order_by(OrdreRemplacement.date_creation.desc()).limit(5).all()
    
    statut = "normal"
    couleur = "vert"
    if bien.est_critique and bien.score_fiabilite is not None:
        if bien.score_fiabilite < 30:
            statut = "critique"
            couleur = "rouge"
        elif bien.score_fiabilite < 60:
            statut = "alerte"
            couleur = "orange"
    
    return {
        "bien_id": bien.id_bien,
        "designation": bien.description or f"Bien #{bien.id_bien}",
        "score_actuel": bien.score_fiabilite,
        "est_critique": bien.est_critique,
        "seuil_alerte": 30 if bien.est_critique else None,
        "statut": statut,
        "couleur": couleur,
        "date_dernier_calcul": bien.date_dernier_calcul_score,
        "vnc_alerte_declenchee": bien.vnc_alerte_declenchee,
        "seuil_alerte_atteint": bien.seuil_alerte_atteint,
        "historique": [
            {
                "date": h.date_evenement,
                "score": h.montant
            }
            for h in historique_scores
        ],
        "maintenances_auto": [
            {
                "id": m.id_maintenance,
                "date_planifiee": m.date_planifiee,
                "statut": m.statut.value if m.statut else None,
                "score_depart": m.score_fiabilite_depart
            }
            for m in maintenances_auto
        ],
        "ordres_remplacement": [
            {
                "id": o.id,
                "motif": o.motif,
                "statut": o.statut.value if o.statut else None,
                "date_creation": o.date_creation,
                "priorite": o.priorite.value if o.priorite else None
            }
            for o in ordres
        ]
    }


@router.post("/{bien_id}/recalculer-score")
async def recalculer_score_fiabilite(
    bien_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Recalcule manuellement le score de fiabilité d'un bien.
    
    ✅ DÉPORTÉ EN ARRIÈRE-PLAN AVEC BackgroundTasks
    ✅ Retourne immédiatement avec statut 202 Accepted
    """
    if not can_update_bien(current_user):
        _deny(current_user, "recalculer_score", "Permissions insuffisantes", resource_id=bien_id)

    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(404, "Bien non trouvé")
    
    # 🔴 CRITIQUE : Déporter le calcul lourd en arrière-plan
    background_tasks.add_task(_calculer_score_async, bien_id)
    
    return {
        "bien_id": bien_id,
        "designation": bien.description or f"Bien #{bien_id}",
        "status": "processing",
        "message": "Calcul du score en cours",
        "check_result_at": f"/api/v1/biens/{bien_id}/score-fiabilite"
    }


@router.get("/critiques")
async def get_biens_critiques(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère la liste des biens critiques avec leur score de fiabilité.
    """
    if not can_view_biens(current_user):
        _deny(current_user, "view_biens_critiques", "Permissions insuffisantes")

    biens = db.query(Bien).filter(
        Bien.est_critique == True,
        Bien.statut_comptable == 'ACTIF'
    ).order_by(Bien.score_fiabilite.asc()).all()
    
    return [
        {
            "id_bien": b.id_bien,
            "designation": b.description or f"Bien #{b.id_bien}",
            "score_fiabilite": b.score_fiabilite,
            "etat": b.etat.value if b.etat else None,
            "est_critique": b.est_critique,
            "seuil_alerte_atteint": b.seuil_alerte_atteint,
            "vnc_alerte_declenchee": b.vnc_alerte_declenchee,
            "couleur": "vert" if b.score_fiabilite >= 60 else 
                       "orange" if b.score_fiabilite >= 30 else "rouge"
        }
        for b in biens
    ]


@router.get("/maintenances-auto/recents")
async def get_maintenances_auto_recents(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les maintenances auto-générées récentes.
    """
    if not can_view_biens(current_user):
        _deny(current_user, "view_maintenances_auto", "Permissions insuffisantes")

    maintenances = db.query(Maintenance).filter(
        Maintenance.origine == TypeOrigineMaintenance.AUTO
    ).order_by(Maintenance.date_creation.desc()).limit(limit).all()
    
    return [
        {
            "id": m.id_maintenance,
            "bien_id": m.id_bien,
            "bien_designation": m.bien.description if m.bien else f"Bien #{m.id_bien}",
            "type_maintenance": m.type_maintenance.value if m.type_maintenance else None,
            "statut": m.statut.value if m.statut else None,
            "date_planifiee": m.date_planifiee,
            "score_fiabilite_depart": m.score_fiabilite_depart,
            "date_creation": m.date_creation
        }
        for m in maintenances
    ]


@router.get("/{bien_id}/ordonnancement-remplacement")
async def get_ordonnancement_remplacement(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère l'ordonnancement de remplacement pour un bien.
    """
    if not can_view_biens(current_user):
        _deny(current_user, "view_ordonnancement", "Permissions insuffisantes", resource_id=bien_id)

    from ...services.audit_service import AuditService
    
    audit_service = AuditService(db)
    arbre = audit_service.get_arbre_remplacement(bien_id)
    verification = audit_service.verifier_chainage_remplacement(bien_id)
    
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(404, "Bien non trouvé")
    
    return {
        "bien_id": bien_id,
        "designation": bien.description or f"Bien #{bien_id}",
        "est_critique": bien.est_critique,
        "score_fiabilite": bien.score_fiabilite,
        "arbre_remplacement": arbre,
        "est_chainage_valide": verification["est_valide"],
        "nombre_remplacements": verification["nombre_remplacements"],
        "recommandation": _get_recommandation_remplacement(bien, arbre)
    }


# ============================================================
# FONCTION AIDE POUR LA RECOMMANDATION
# ============================================================

def _get_recommandation_remplacement(bien, arbre) -> str:
    """Génère une recommandation de remplacement."""
    if not bien.est_critique:
        return "Bien non critique - Surveillance standard"
    
    if bien.score_fiabilite is None:
        return "Score non calculé - Veuillez recalculer"
    
    if bien.score_fiabilite < 30:
        if len(arbre) > 1:
            return "Remplacement recommandé - Un remplacement a déjà été effectué"
        return "Remplacement urgent recommandé"
    elif bien.score_fiabilite < 60:
        return "Surveillance renforcée - Planifier un remplacement à moyen terme"
    else:
        return "État satisfaisant - Continuer la maintenance préventive"