# app/api/endpoints/concertations.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...models.discussion_concertation import TypeValidationEnum, DecisionValidationConcertation
from ...schemas.concertation import (
    DiscussionConcertationCreate,
    DiscussionConcertationResponse,
    DiscussionConcertationStatusResponse,
    MessageConcertationCreate,
    MessageConcertationResponse,
    ValidationConcertationCreate,
    ValidationConcertationResponse
)
from ...services.concertation_service import ConcertationService

router = APIRouter(prefix="/concertations", tags=["Concertations"])

def check_concertation_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    if not user.role:
        return False
    role = user.role.nom.upper()
    return role in ["ADMIN", "DG", "COMPTABLE"]

def is_validator(user: Utilisateur) -> bool:
    if not user or not user.role:
        return False
    role = user.role.nom.upper()
    return role in ["DG", "COMPTABLE"]

@router.get("/bien/{bien_id}", response_model=List[DiscussionConcertationResponse])
async def get_discussions_by_bien(
    bien_id: int,
    type_validation: Optional[str] = Query(None, description="Filtrer par type de validation (CESSION ou REBUT)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(status_code=404, detail="Bien non trouvé")

    service = ConcertationService(db)
    discussions = service.get_discussions_by_bien(bien_id, type_validation)

    resultats = []
    for disc in discussions:
        designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
        response = DiscussionConcertationResponse(
            id=disc.id,
            id_bien=disc.id_bien,
            bien_designation=designation,
            type_validation=disc.type_validation,
            titre=disc.titre,
            est_active=disc.est_active,
            date_creation=disc.date_creation,
            date_cloture=disc.date_cloture,
            messages=[],
            validations=[],
            statut_validation="EN_ATTENTE"
        )
        resultats.append(response)

    return resultats

@router.post("/", response_model=DiscussionConcertationResponse, status_code=status.HTTP_201_CREATED)
async def creer_discussion(
    data: DiscussionConcertationCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    if not is_validator(current_user):
        raise HTTPException(status_code=403, detail="Seuls le DG et le Comptable peuvent créer une discussion")

    service = ConcertationService(db)
    try:
        discussion = service.creer_discussion(data, current_user.id)
        return discussion
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{discussion_id}", response_model=DiscussionConcertationResponse)
async def get_discussion(
    discussion_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    discussion = service.get_discussion(discussion_id)

    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion non trouvée")

    bien = db.query(Bien).filter(Bien.id_bien == discussion.id_bien).first()
    designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{discussion.id_bien}"

    messages = []
    for msg in discussion.messages:
        utilisateur = db.query(Utilisateur).filter(Utilisateur.id == msg.id_utilisateur).first()
        messages.append({
            "id": msg.id,
            "id_discussion": msg.id_discussion,
            "id_utilisateur": msg.id_utilisateur,
            "nom_validateur": utilisateur.nom if utilisateur else "Inconnu",
            "prenom_validateur": utilisateur.prenom if utilisateur else "",
            "role_validateur": utilisateur.role.nom.upper() if utilisateur and utilisateur.role else "UNKNOWN",
            "contenu": msg.contenu,
            "parent_id": msg.parent_id,
            "date_creation": msg.date_creation,
            "est_modifie": msg.est_modifie,
            "date_modification": msg.date_modification,
            "reponses": []
        })

    validations = []
    for val in discussion.validations:
        utilisateur = db.query(Utilisateur).filter(Utilisateur.id == val.id_validateur).first()
        validations.append({
            "id": val.id,
            "id_discussion": val.id_discussion,
            "id_validateur": val.id_validateur,
            "nom_validateur": utilisateur.nom if utilisateur else "Inconnu",
            "prenom_validateur": utilisateur.prenom if utilisateur else "",
            "role_validateur": utilisateur.role.nom.upper() if utilisateur and utilisateur.role else "UNKNOWN",
            "decision": val.decision,
            "commentaire": val.commentaire,
            "date_decision": val.date_decision
        })

    statut = service.get_statut_discussion(discussion_id)

    return DiscussionConcertationResponse(
        id=discussion.id,
        id_bien=discussion.id_bien,
        bien_designation=designation,
        type_validation=discussion.type_validation,
        titre=discussion.titre,
        est_active=discussion.est_active,
        date_creation=discussion.date_creation,
        date_cloture=discussion.date_cloture,
        messages=messages,
        validations=validations,
        statut_validation=statut["statut_global"]
    )

@router.post("/{discussion_id}/cloturer", response_model=DiscussionConcertationResponse)
async def cloturer_discussion(
    discussion_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    try:
        discussion = service.cloturer_discussion(discussion_id)
        return discussion
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{discussion_id}/statut", response_model=DiscussionConcertationStatusResponse)
async def get_statut_discussion(
    discussion_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    statut = service.get_statut_discussion(discussion_id)

    discussion = service.get_discussion(discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion non trouvée")

    return DiscussionConcertationStatusResponse(
        id_discussion=discussion_id,
        id_bien=discussion.id_bien,
        type_validation=discussion.type_validation,
        validation_dg=statut["validation_dg"],
        validation_comptable=statut["validation_comptable"],
        est_valide=statut["est_valide"],
        date_validation_comptable=statut["date_validation_comptable"],
        date_validation_dg=statut["date_validation_dg"],
        statut_global=statut["statut_global"]
    )

@router.get("/bien/{bien_id}/eligibilite/{type_validation}")
async def verifier_eligibilite_action(
    bien_id: int,
    type_validation: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    if type_validation.upper() not in ["CESSION", "REBUT"]:
        raise HTTPException(status_code=400, detail="Type de validation invalide")

    service = ConcertationService(db)
    result = service.verifier_eligibilite_action(bien_id, type_validation.upper())

    return result

@router.get("/detecter/preview")
async def preview_biens_eligibles(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Affiche les biens éligibles à une discussion (lecture seule, sans création).
    Utile pour prévisualiser avant de déclencher la création automatique.
    """
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    try:
        resultats = service.detecter_biens_eligibles()
        return {
            "message": f"Prévisualisation : {len(resultats)} bien(s) éligible(s)",
            "biens": resultats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detecter")
async def detecter_et_creer_discussions(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Détecte les biens éligibles (rebut / cession) et crée automatiquement
    une discussion de concertation pour chacun qui n'en a pas déjà une active.
    """
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    try:
        resultat = service.creer_discussions_automatiques()
        return {
            "message": (
                f"{resultat['creees']} discussion(s) créée(s), "
                f"{resultat['ignorees']} ignorée(s) (doublon), "
                f"{resultat['erreurs']} erreur(s) "
                f"sur {resultat['total_eligibles']} bien(s) éligible(s)"
            ),
            **resultat
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{discussion_id}/messages", response_model=MessageConcertationResponse, status_code=status.HTTP_201_CREATED)
async def ajouter_message(
    discussion_id: int,
    data: MessageConcertationCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    try:
        message = service.ajouter_message(discussion_id, data, current_user.id)
        
        utilisateur = db.query(Utilisateur).filter(Utilisateur.id == message.id_utilisateur).first()
        
        return MessageConcertationResponse(
            id=message.id,
            id_discussion=message.id_discussion,
            id_utilisateur=message.id_utilisateur,
            nom_validateur=utilisateur.nom if utilisateur else "Inconnu",
            prenom_validateur=utilisateur.prenom if utilisateur else "",
            role_validateur=utilisateur.role.nom.upper() if utilisateur and utilisateur.role else "UNKNOWN",
            contenu=message.contenu,
            parent_id=message.parent_id,
            date_creation=message.date_creation,
            est_modifie=message.est_modifie,
            date_modification=message.date_modification,
            reponses=[]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/messages/{message_id}", response_model=MessageConcertationResponse)
async def modifier_message(
    message_id: int,
    contenu: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = ConcertationService(db)
    try:
        message = service.modifier_message(message_id, contenu, current_user.id)
        
        utilisateur = db.query(Utilisateur).filter(Utilisateur.id == message.id_utilisateur).first()
        
        return MessageConcertationResponse(
            id=message.id,
            id_discussion=message.id_discussion,
            id_utilisateur=message.id_utilisateur,
            nom_validateur=utilisateur.nom if utilisateur else "Inconnu",
            prenom_validateur=utilisateur.prenom if utilisateur else "",
            role_validateur=utilisateur.role.nom.upper() if utilisateur and utilisateur.role else "UNKNOWN",
            contenu=message.contenu,
            parent_id=message.parent_id,
            date_creation=message.date_creation,
            est_modifie=message.est_modifie,
            date_modification=message.date_modification,
            reponses=[]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{discussion_id}/valider", response_model=ValidationConcertationResponse)
async def enregistrer_validation(
    discussion_id: int,
    data: ValidationConcertationCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_concertation_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    if not is_validator(current_user):
        raise HTTPException(status_code=403, detail="Seuls le DG et le Comptable peuvent valider")

    service = ConcertationService(db)
    try:
        validation = service.enregistrer_validation(discussion_id, data, current_user.id)
        
        utilisateur = db.query(Utilisateur).filter(Utilisateur.id == validation.id_validateur).first()
        
        return ValidationConcertationResponse(
            id=validation.id,
            id_discussion=validation.id_discussion,
            id_validateur=validation.id_validateur,
            nom_validateur=utilisateur.nom if utilisateur else "Inconnu",
            prenom_validateur=utilisateur.prenom if utilisateur else "",
            role_validateur=utilisateur.role.nom.upper() if utilisateur and utilisateur.role else "UNKNOWN",
            decision=validation.decision,
            commentaire=validation.commentaire,
            date_decision=validation.date_decision
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))