# app/api/endpoints/cessions.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import List

logger = logging.getLogger(__name__)

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...schemas.cession import CessionCreate, CessionResponse, RebutCreate
from ...schemas.ecriture_comptable import EcritureResponse
from ...services.comptabilite_service import ComptabiliteService
from ...services.validation_service import ValidationService

router = APIRouter(prefix="/cessions", tags=["Cessions"])


def check_cession_permission(user: Utilisateur) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "COMPTABLE", "DG"]


# ============================================================
# ENDPOINT D'ÉLIGIBILITÉ
# ============================================================
@router.get("/eligibilite/{bien_id}")
async def get_eligibilite(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Retourne l'éligibilité à la cession et au rebut pour un bien donné.
    """
    if not check_cession_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    validation_service = ValidationService(db)
    elig_cession = validation_service.verifier_eligibilite_cession(bien_id)
    elig_rebut = validation_service.verifier_eligibilite_rebut(bien_id)

    return {
        "cession": elig_cession,
        "rebut": elig_rebut
    }


# ============================================================
# ENDPOINTS D'EXÉCUTION AVEC VERROU DE SÉCURITÉ
# ============================================================
@router.post("/", status_code=status.HTTP_201_CREATED)
async def creer_cession(
    data: CessionCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_cession_permission(current_user):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # 🔒 Vérification d'éligibilité avant exécution
    validation_service = ValidationService(db)
    elig = validation_service.verifier_eligibilite_cession(data.id_bien)
    if not elig["eligible"]:
        raise HTTPException(status_code=400, detail=elig["raison"])

    bien = db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
    if not bien:
        raise HTTPException(status_code=404, detail="Bien non trouvé")

    try:
        service = ComptabiliteService(db, cree_par_id=current_user.id)
        cession, ecritures = service.enregistrer_cession(data)
        return {
            "cession": CessionResponse.model_validate(cession),
            "ecritures": ecritures,
            "message": f"Cession enregistrée — {len(ecritures)} écriture(s) générée(s)",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rebut", response_model=List[EcritureResponse], status_code=status.HTTP_201_CREATED)
async def mettre_au_rebut(
    data: RebutCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    logger.info(
        "[REBUT] Tentative de mise au rebut | bien_id=%s | user=%s (role=%s)",
        data.id_bien,
        current_user.id if current_user else "inconnu",
        current_user.role.nom if current_user and current_user.role else "?",
    )

    if not check_cession_permission(current_user):
        logger.warning(
            "[REBUT] 403 Permissions insuffisantes | user=%s (role=%s)",
            current_user.id if current_user else "inconnu",
            current_user.role.nom if current_user and current_user.role else "?",
        )
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # 🔒 Vérification d'éligibilité avant exécution
    validation_service = ValidationService(db)
    elig = validation_service.verifier_eligibilite_rebut(data.id_bien)

    logger.info(
        "[REBUT] Résultat éligibilité | bien_id=%s | eligible=%s | diagnostic=%s | valid_dg=%s | valid_comptable=%s | raison='%s'",
        data.id_bien,
        elig.get("eligible"),
        elig.get("diagnostic_irrecuperable"),
        elig.get("validation_dg"),
        elig.get("validation_comptable"),
        elig.get("raison", ""),
    )

    if not elig["eligible"]:
        logger.warning(
            "[REBUT] 400 Bien non éligible | bien_id=%s | raison='%s'",
            data.id_bien,
            elig["raison"],
        )
        raise HTTPException(status_code=400, detail=elig["raison"])

    try:
        service = ComptabiliteService(db, cree_par_id=current_user.id)
        ecritures = service.enregistrer_rebut(data)
        logger.info(
            "[REBUT] ✅ Mise au rebut enregistrée | bien_id=%s | %d écriture(s) générée(s)",
            data.id_bien,
            len(ecritures),
        )
        return ecritures
    except ValueError as e:
        logger.error(
            "[REBUT] 400 ValueError lors de l'enregistrement | bien_id=%s | erreur='%s'",
            data.id_bien,
            str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(
            "[REBUT] 500 Erreur inattendue | bien_id=%s | erreur='%s'",
            data.id_bien,
            str(e),
        )
        raise