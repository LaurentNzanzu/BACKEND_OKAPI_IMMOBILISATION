# backend/app/api/endpoints/mouvements.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from ...core.database import get_db
from ...schemas.mouvement import MouvementCreate, MouvementUpdate, MouvementResponse, MouvementListResponse
from ...services.mouvement_service import MouvementService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/mouvements", tags=["Mouvements"])

# ✅ LOGIQUE DE PERMISSIONS SELON LE TABLEAU
# TRANSFERT    → COMPTABLE + TECHNICIEN
# AFFECTATION  → COMPTABLE + TECHNICIEN
# RETOUR       → TECHNICIEN seulement
# SORTIE       → COMPTABLE + TECHNICIEN
# CESSION      → COMPTABLE seulement
# ADMIN/DG     → Tous les droits

TYPES_PAR_ROLE = {
    "ADMIN":      ["TRANSFERT", "AFFECTATION", "RETOUR", "SORTIE", "CESSION"],
    "DG":         ["TRANSFERT", "AFFECTATION", "RETOUR", "SORTIE", "CESSION"],
    "COMPTABLE":  ["TRANSFERT", "AFFECTATION", "SORTIE", "CESSION"],
    "TECHNICIEN": ["TRANSFERT", "AFFECTATION", "RETOUR", "SORTIE"],
}

def check_mouvement_permission(user: Utilisateur, action: str, type_mouvement: Optional[str] = None) -> bool:
    """Vérifie les permissions selon le tableau des rôles."""
    if not user:
        return False
    
    role = user.role.nom.upper() if user.role else "USER"
    
    # ADMIN et DG ont tous les droits
    if role in ["ADMIN", "DG"]:
        return True
    
    # Vérification selon le type de mouvement
    types_autorises = TYPES_PAR_ROLE.get(role, [])
    
    if action == "create":
        # Pour créer, le type doit être dans la liste du rôle
        if type_mouvement and type_mouvement.upper() in types_autorises:
            return True
        return False
    
    if action == "view":
        # Tous les rôles du tableau peuvent voir
        return role in TYPES_PAR_ROLE
    
    return False

def get_types_autorises(user: Utilisateur) -> List[str]:
    """Retourne la liste des types de mouvement autorisés pour un utilisateur."""
    if not user:
        return []
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]:
        return ["TRANSFERT", "AFFECTATION", "RETOUR", "SORTIE", "CESSION"]
    return TYPES_PAR_ROLE.get(role, [])

@router.post("/", response_model=MouvementResponse, status_code=status.HTTP_201_CREATED)
async def creer_mouvement(
    data: MouvementCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    # ✅ Vérification spécifique : le type doit être autorisé pour ce rôle
    if not check_mouvement_permission(current_user, "create", data.type_mouvement.value):
        raise HTTPException(
            status_code=403,
            detail=f"Permissions insuffisantes pour créer un mouvement de type {data.type_mouvement.value}"
        )
    
    service = MouvementService(db)
    audit_service = AuditService(db)

    try:
        mouvement = service.creer_mouvement(data, current_user.id)
        
        # Enregistrer l'audit
        audit_service.log_create(
            user_id=current_user.id,
            table_name="mouvements_biens",
            record_id=mouvement.id_mouvement,
            new_values={
                "id_bien": data.id_bien,
                "type_mouvement": data.type_mouvement.value,
                "raison": data.raison,
                "date_mouvement": str(data.date_mouvement) if data.date_mouvement else None
            },
            request=request
        )
        
        return mouvement
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erreur interne lors de la création du mouvement")

@router.get("/bien/{id_bien}", response_model=List[MouvementResponse])
async def get_mouvements_by_bien(
    id_bien: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_mouvement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MouvementService(db)
    mouvements = service.get_mouvements_by_bien(id_bien, skip, limit)

    for mvt in mouvements:
        if mvt.bien:
            mvt.bien_designation = f"{getattr(mvt.bien, 'marque', '') or getattr(mvt.bien, 'fabricant', '')} {getattr(mvt.bien, 'modele', '')}".strip()
        if mvt.utilisateur:
            mvt.utilisateur_nom = f"{mvt.utilisateur.prenom} {mvt.utilisateur.nom}"

    return mouvements

@router.get("/", response_model=MouvementListResponse)
async def get_all_mouvements(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    type_mouvement: Optional[str] = Query(None, description="Filtrer par type de mouvement"),
    date_debut: Optional[str] = Query(None, description="Date de début (YYYY-MM-DD)"),
    date_fin: Optional[str] = Query(None, description="Date de fin (YYYY-MM-DD)"),
    id_bien: Optional[int] = Query(None, description="Filtrer par ID de bien"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_mouvement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    date_debut_dt = datetime.strptime(date_debut, "%Y-%m-%d") if date_debut else None
    date_fin_dt = datetime.strptime(date_fin, "%Y-%m-%d") if date_fin else None

    service = MouvementService(db)
    mouvements = service.get_all_mouvements(
        skip=skip,
        limit=limit,
        type_mouvement=type_mouvement,
        date_debut=date_debut_dt,
        date_fin=date_fin_dt,
        id_bien=id_bien
    )

    total_query = service.get_all_mouvements(
        type_mouvement=type_mouvement,
        date_debut=date_debut_dt,
        date_fin=date_fin_dt,
        id_bien=id_bien
    )
    total = len(total_query)

    for mvt in mouvements:
        if mvt.bien:
            mvt.bien_designation = f"{getattr(mvt.bien, 'marque', '') or getattr(mvt.bien, 'fabricant', '')} {getattr(mvt.bien, 'modele', '')}".strip()
        if mvt.utilisateur:
            mvt.utilisateur_nom = f"{mvt.utilisateur.prenom} {mvt.utilisateur.nom}"

    return MouvementListResponse(
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
        mouvements=mouvements
    )

@router.get("/{id_mouvement}", response_model=MouvementResponse)
async def get_mouvement(
    id_mouvement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_mouvement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MouvementService(db)
    mouvement = service.get_mouvement(id_mouvement)

    if not mouvement:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")

    if mouvement.bien:
        mouvement.bien_designation = f"{getattr(mouvement.bien, 'marque', '') or getattr(mouvement.bien, 'fabricant', '')} {getattr(mouvement.bien, 'modele', '')}".strip()
    if mouvement.utilisateur:
        mouvement.utilisateur_nom = f"{mouvement.utilisateur.prenom} {mouvement.utilisateur.nom}"

    return mouvement

@router.put("/{id_mouvement}", response_model=MouvementResponse)
async def update_mouvement(
    id_mouvement: int,
    data: MouvementUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_mouvement_permission(current_user, "edit"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MouvementService(db)
    audit_service = AuditService(db)

    old_mouvement = service.get_mouvement(id_mouvement)
    if not old_mouvement:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")

    mouvement = service.update_mouvement(id_mouvement, data)
    if not mouvement:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")

    audit_service.log_update(
        user_id=current_user.id,
        table_name="mouvements_biens",
        record_id=id_mouvement,
        old_values={"raison": old_mouvement.raison},
        new_values={"raison": data.raison},
        request=request
    )

    return mouvement

@router.get("/statistiques")
async def get_statistiques(
    annee: Optional[int] = Query(None, description="Année pour les statistiques"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_mouvement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MouvementService(db)
    return service.get_statistiques_mouvements(annee)

# ✅ NOUVEL ENDPOINT : Retourne les types autorisés pour le frontend
@router.get("/types-autorises")
async def get_types_autorises(
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne la liste des types de mouvement autorisés pour l'utilisateur connecté."""
    return {"types": get_types_autorises(current_user)}