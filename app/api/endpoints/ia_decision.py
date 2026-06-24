# backend/app/api/endpoints/ia_decision.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import logging
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.ia_decision_service import IADecisionService
from ...schemas.decision_ia import AssistantRequest, AssistantResponse 

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ia", tags=["IA Decision"])

def check_ia_permission(user: Utilisateur) -> bool:
    """Vérifie si l'utilisateur a le droit d'accéder aux fonctionnalités IA"""
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    return role in ["ADMIN", "DG", "COMPTABLE", "MAGASINIER"]  


# ========== PHASE 1.1 : HEALTH SCORE ==========
@router.get("/health-score/{bien_id}", response_model=Dict[str, Any])
async def get_health_score(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Calcule et retourne le Health Score pour un bien spécifique.
    Note: 0-100 - EXCELLENT, SURVEILLE, CRITIQUE, URGENT
    """
    if not check_ia_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes. Accès réservé à ADMIN, DG et COMPTABLE."
        )

    service = IADecisionService(db)
    try:
        result = service.calculer_health_score(bien_id, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur serveur lors du calcul du Health Score: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )


# ========== PHASE 1.1 : RECOMMANDATIONS PARC ==========
@router.get("/recommandations/parc", response_model=List[Dict[str, Any]])
async def get_recommandations_parc(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les recommandations IA pour l'ensemble du parc immobilier.
    Retourne une liste des Health Scores de tous les biens.
    """
    if not check_ia_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes. Accès réservé à ADMIN, DG et COMPTABLE."
        )

    service = IADecisionService(db)
    try:
        result = service.generer_recommandations_parc(current_user.id)
        return result
    except Exception as e:
        logger.error(f"Erreur lors de la génération des recommandations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )


# ========== PHASE 1.2 : DÉCISION STRATÉGIQUE (CONSERVER vs REMPLACER) ==========
@router.get("/decision/{bien_id}", response_model=Dict[str, Any])
async def get_decision_strategique(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Génère une analyse stratégique Conserver vs Remplacer pour un bien.
    Basée sur les coûts d'amortissement, maintenance, et l'estimation du remplacement.
    Recommande le remplacement si économie > 15%.
    """
    if not check_ia_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes. Accès réservé à ADMIN, DG et COMPTABLE."
        )

    service = IADecisionService(db)
    
    try:
        result = service.generer_decision_strategique(bien_id, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur génération décision stratégique: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de l'analyse."
        )
    
# --- PHASE 1.3 : ENDPOINT ALERTES ACHAT ---
@router.get("/pieces/alertes-achat", response_model=List[Dict[str, Any]])
async def get_alertes_achat_pieces(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Génère des alertes d'achat pour les pièces dont le stock est insuffisant.
    Retourne une liste des pièces nécessitant un réapprovisionnement.
    """
    if not check_ia_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes. Accès réservé à ADMIN, DG et COMPTABLE."
        )

    service = IADecisionService(db)
    
    try:
        result = service.generer_alertes_achat_pieces(current_user.id)
        return result
    except Exception as e:
        logger.error(f"Erreur lors de la génération des alertes d'achat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )
    
# --- PHASE 1.4 : ENDPOINT ASSISTANT CONVERSATIONNEL ---
@router.post("/assistant", response_model=Dict[str, Any])
async def assistant_conversationnel(
    request: AssistantRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Assistant IA conversationnel. Posez des questions en langage naturel.
    
    Exemples:
    - "Quels équipements doivent être remplacés ?"
    - "Quelles sont les pièces à commander ?"
    - "Quels biens sont totalement amortis ?"
    - "Quelle est la santé du parc ?"
    """
    if not check_ia_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes. Accès réservé à ADMIN, DG et COMPTABLE."
        )
    
    if not request.question or len(request.question.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La question doit contenir au moins 3 caractères."
        )

    service = IADecisionService(db)
    
    try:
        result = service.assister_conversationnel(request.question, current_user.id)
        return result
    except Exception as e:
        logger.error(f"Erreur lors de l'analyse de la question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du serveur"
        )