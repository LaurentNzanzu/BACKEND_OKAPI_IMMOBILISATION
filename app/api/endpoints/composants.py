# backend/app/api/endpoints/composants.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
from ...core.database import get_db
# ═══ AJOUT 5.20.i — Dépendance module ═══
from ...core.dependencies_modules import require_module
# ═══ FIN AJOUT 5.20.i ═══
from ...schemas.composant import ComposantCreate, ComposantUpdate, ComposantResponse, ComposantListResponse
from ...services.composant_service import ComposantService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...models.vehicule import Vehicule
from ...models.machine import Machine
from ...models.ordinateur import Ordinateur

# ═══ MODIF 5.20.i — require_module sur le router ═══
router = APIRouter(
    prefix="/composants",
    tags=["Composants"],
    dependencies=[Depends(require_module("IMMOBILISATION"))],
)
# ═══ FIN MODIF 5.20.i ═══


def check_composant_permission(user: Utilisateur, action: str) -> bool:
    if not user: 
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]: 
        return True
    if role == "COMPTABLE" and action in ["view", "create", "update", "delete"]: 
        return True
    if role == "TECHNICIEN" and action == "view": 
        return True
    return action == "view"


def get_bien_designation(bien) -> str:
    type_bien = getattr(bien, 'type_bien', None)
    
    if type_bien == 'vehicule' or isinstance(bien, Vehicule):
        marque = getattr(bien, 'marque', '')
        modele = getattr(bien, 'modele', '')
        designation = f"{marque} {modele}".strip()
        if designation:
            return designation
        return f"Véhicule #{bien.id_bien}"
    
    elif type_bien == 'machine' or isinstance(bien, Machine):
        fabricant = getattr(bien, 'fabricant', '')
        modele = getattr(bien, 'modele', '')
        designation = f"{fabricant} {modele}".strip()
        if designation:
            return designation
        return f"Machine #{bien.id_bien}"
    
    elif type_bien == 'ordinateur' or isinstance(bien, Ordinateur):
        marque = getattr(bien, 'marque', '')
        modele = getattr(bien, 'modele', '')
        designation = f"{marque} {modele}".strip()
        if designation:
            return designation
        return f"Ordinateur #{bien.id_bien}"
    
    return f"Bien #{bien.id_bien}"


# ═══ AJOUT 5.20.i — Helpers d'isolation multi-tenant ═══
def _is_platform_admin(user: Utilisateur) -> bool:
    """Retourne True si l'utilisateur est ADMIN plateforme (organisation_id NULL)."""
    return bool(getattr(user, "is_platform_admin", False))


def _check_acces_bien_id(db: Session, current_user: Utilisateur, bien_id: int) -> Bien:
    """
    Vérifie l'accès à un Bien par son ID.
    - ADMIN plateforme → accès total
    - Sinon : le bien doit appartenir à la même ONG
    - Bien sans organisation_id → refusé (donnée historique)
    Retourne le Bien si autorisé, lève 403 sinon.
    """
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(status_code=404, detail=f"Bien #{bien_id} non trouvé")

    if _is_platform_admin(current_user):
        return bien

    bien_org = getattr(bien, "organisation_id", None)
    if bien_org is None:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Accès refusé : bien #{bien_id} sans organisation "
                f"(donnée historique). Contactez l'administrateur plateforme."
            ),
        )
    if bien_org != current_user.organisation_id:
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : bien #{bien_id} appartient à une autre organisation.",
        )
    return bien


def _check_acces_composant(db: Session, current_user: Utilisateur, composant) -> None:
    """
    Vérifie l'accès à un Composant via son Bien parent.
    Lève 403 si interdit.
    """
    if _is_platform_admin(current_user):
        return

    if not composant or not getattr(composant, "id_bien", None):
        raise HTTPException(status_code=404, detail="Composant non trouvé")

    # Utiliser _check_acces_bien_id qui gère déjà toute la logique
    _check_acces_bien_id(db, current_user, composant.id_bien)
# ═══ FIN AJOUT 5.20.i ═══


@router.post("/", response_model=ComposantResponse, status_code=status.HTTP_201_CREATED)
async def create_composant(
    data: ComposantCreate, 
    db: Session = Depends(get_db), 
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_composant_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ AJOUT 5.20.i — Vérification d'accès sur le bien ciblé ═══
    _check_acces_bien_id(db, current_user, data.id_bien)
    # ═══ FIN AJOUT 5.20.i ═══

    service = ComposantService(db)
    audit_service = AuditService(db)
    
    try:
        composant = service.create_composant(data)
        
        # Enregistrer l'audit
        audit_service.log_create(
            user_id=current_user.id,
            table_name="composants",
            record_id=composant.id_composant,
            new_values={
                "id_bien": data.id_bien,
                "designation": data.designation,
                "valeur": data.valeur,
                "duree_vie_ans": data.duree_vie_ans
            },
            request=request
        )
        
        return service.to_response(composant, db.query(Bien).filter(Bien.id_bien == composant.id_bien).first())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/bien/{bien_id}", response_model=ComposantListResponse)
async def get_composants_by_bien(
    bien_id: int, 
    db: Session = Depends(get_db), 
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_composant_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ AJOUT 5.20.i — Vérification d'accès sur le bien ═══
    bien = _check_acces_bien_id(db, current_user, bien_id)
    # ═══ FIN AJOUT 5.20.i ═══

    service = ComposantService(db)
    composants = service.get_composants_by_bien(bien_id)
    return ComposantListResponse(
        total=len(composants),
        composants=[service.to_response(c, bien) for c in composants],
    )


@router.get("/{composant_id}", response_model=ComposantResponse)
async def get_composant(
    composant_id: int, 
    db: Session = Depends(get_db), 
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_composant_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = ComposantService(db)
    composant = service.get_composant(composant_id)
    if not composant:
        raise HTTPException(status_code=404, detail="Composant non trouvé")

    # ═══ AJOUT 5.20.i — Vérification d'accès ═══
    _check_acces_composant(db, current_user, composant)
    # ═══ FIN AJOUT 5.20.i ═══

    bien = db.query(Bien).filter(Bien.id_bien == composant.id_bien).first()
    return service.to_response(composant, bien)


@router.put("/{composant_id}", response_model=ComposantResponse)
async def update_composant(
    composant_id: int, 
    data: ComposantUpdate, 
    db: Session = Depends(get_db), 
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_composant_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ComposantService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancien composant
    old_composant = service.get_composant(composant_id)
    if not old_composant:
        raise HTTPException(status_code=404, detail="Composant non trouvé")

    # ═══ AJOUT 5.20.i — Vérification d'accès avant modification ═══
    _check_acces_composant(db, current_user, old_composant)
    # ═══ FIN AJOUT 5.20.i ═══
    
    composant = service.update_composant(composant_id, data)
    if not composant:
        raise HTTPException(status_code=404, detail="Composant non trouvé")
    
    # Enregistrer l'audit
    audit_service.log_update(
        user_id=current_user.id,
        table_name="composants",
        record_id=composant_id,
        old_values={
            "designation": old_composant.designation,
            "valeur": old_composant.valeur,
            "duree_vie_ans": old_composant.duree_vie_ans
        },
        new_values={
            "designation": composant.designation,
            "valeur": composant.valeur,
            "duree_vie_ans": composant.duree_vie_ans
        },
        request=request
    )
    
    bien = db.query(Bien).filter(Bien.id_bien == composant.id_bien).first()
    return service.to_response(composant, bien)


@router.delete("/{composant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_composant(
    composant_id: int, 
    db: Session = Depends(get_db), 
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_composant_permission(current_user, "delete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = ComposantService(db)
    audit_service = AuditService(db)
    
    # Récupérer le composant avant suppression
    composant = service.get_composant(composant_id)
    if not composant:
        raise HTTPException(status_code=404, detail="Composant non trouvé")

    # ═══ AJOUT 5.20.i — Vérification d'accès avant suppression ═══
    _check_acces_composant(db, current_user, composant)
    # ═══ FIN AJOUT 5.20.i ═══
    
    # Enregistrer l'audit
    audit_service.log_delete(
        user_id=current_user.id,
        table_name="composants",
        record_id=composant_id,
        old_values={
            "id_bien": composant.id_bien,
            "designation": composant.designation,
            "valeur": composant.valeur,
            "duree_vie_ans": composant.duree_vie_ans
        },
        request=request
    )
    
    if not service.delete_composant(composant_id):
        raise HTTPException(status_code=404, detail="Composant non trouvé")


@router.get("/bien/{bien_id}/analyse")
async def analyse_composants_bien(
    bien_id: int, 
    db: Session = Depends(get_db), 
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_composant_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # ═══ AJOUT 5.20.i — Vérification d'accès sur le bien ═══
    bien = _check_acces_bien_id(db, current_user, bien_id)
    # ═══ FIN AJOUT 5.20.i ═══
    
    service = ComposantService(db)
    
    type_bien = bien.type_bien
    marque = None
    modele = None
    designation = f"Bien #{bien_id}"
    
    if type_bien == 'vehicule':
        vehicule = db.query(Vehicule).filter(Vehicule.id_bien == bien_id).first()
        if vehicule:
            marque = vehicule.marque
            modele = vehicule.modele
            designation = f"{marque} {modele}".strip() or designation
    elif type_bien == 'machine':
        machine = db.query(Machine).filter(Machine.id_bien == bien_id).first()
        if machine:
            marque = machine.fabricant
            modele = machine.modele
            designation = f"{marque} {modele}".strip() or designation
    elif type_bien == 'ordinateur':
        ordinateur = db.query(Ordinateur).filter(Ordinateur.id_bien == bien_id).first()
        if ordinateur:
            marque = ordinateur.marque
            modele = ordinateur.modele
            designation = f"{marque} {modele}".strip() or designation
    
    composants = service.get_composants_by_bien(bien_id)
    somme_composants = service.get_valeur_totale_composants(bien_id)
    valeur_structure = float(bien.prix_acquisition) - somme_composants
    
    return {
        "bien_id": bien_id,
        "bien_designation": designation,
        "valeur_totale_bien": float(bien.prix_acquisition),
        "valeur_totale_composants": somme_composants,
        "valeur_structure": valeur_structure,
        "nombre_composants": len(composants),
        "composants": [
            {
                "id": c.id_composant,
                "designation": c.designation,
                "valeur": c.valeur,
                "pourcentage": round((c.valeur / float(bien.prix_acquisition)) * 100, 2) if bien.prix_acquisition > 0 else 0,
                "duree_vie_ans": c.duree_vie_ans
            } for c in composants
        ],
        "conformite_ohada": {
            "est_conforme": len(composants) > 0,
            "message": "Bien décomposé en composants" if len(composants) > 0 else "Aucun composant défini (amortissement global recommandé)"
        }
    }