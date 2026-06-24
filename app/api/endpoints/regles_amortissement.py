from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.regle_amortissement import (
    RegleAmortissementCreate,
    RegleAmortissementUpdate,
    RegleAmortissementResponse
)
from ...services.amortissement_service import AmortissementService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.regles_amortissement import RegleAmortissement

router = APIRouter(prefix="/regles-amortissement", tags=["Règles Amortissement"])

def check_regle_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG", "COMPTABLE"]:
        return True
    return action == "view"

@router.get("/", response_model=List[RegleAmortissementResponse])
async def get_all_regles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_regle_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    regles = db.query(RegleAmortissement).offset(skip).limit(limit).all()
    return regles

@router.get("/{categorie}", response_model=RegleAmortissementResponse)
async def get_regle_by_categorie(
    categorie: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_regle_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    regle = service.get_regle_par_categorie(categorie)
    if not regle:
        raise HTTPException(status_code=404, detail=f"Règle non trouvée pour la catégorie: {categorie}")
    return regle

@router.post("/", response_model=RegleAmortissementResponse, status_code=status.HTTP_201_CREATED)
async def create_regle(
    data: RegleAmortissementCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_regle_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    existing = db.query(RegleAmortissement).filter(
        RegleAmortissement.categorie_bien == data.categorie_bien
    ).first()
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Une règle existe déjà pour la catégorie: {data.categorie_bien}"
        )
    
    regle = RegleAmortissement(
        categorie_bien=data.categorie_bien,
        duree_vie_ans=data.duree_vie_ans,
        taux_fiscal=data.taux_fiscal,
        coeff_deg_3_4_ans=data.coeff_deg_3_4_ans,
        coeff_deg_5_6_ans=data.coeff_deg_5_6_ans,
        coeff_deg_7_plus_ans=data.coeff_deg_7_plus_ans,
        compte_dotation=data.compte_dotation,
        compte_amortissement=data.compte_amortissement,
        compte_depreciation=data.compte_depreciation,
        base_jours_annee=data.base_jours_annee,
        prorata_debut_mois=data.prorata_debut_mois,
        est_active=data.est_active,
        modifie_par=current_user.nom if current_user else "systeme"
    )
    
    db.add(regle)
    db.commit()
    db.refresh(regle)
    return regle

@router.put("/{id_regle}", response_model=RegleAmortissementResponse)
async def update_regle(
    id_regle: int,
    data: RegleAmortissementUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else ""
    if role not in ["ADMIN", "DG"]:
        raise HTTPException(
            status_code=403,
            detail="Seul l'administrateur ou le DG peut modifier les règles",
        )

    if not check_regle_permission(current_user, "edit"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    update_data = data.model_dump(exclude_unset=True)
    regle = service.update_regle_configuration(id_regle, update_data, current_user.nom_utilisateur)
    
    if not regle:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    
    return regle

@router.delete("/{id_regle}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_regle(
    id_regle: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else ""
    if role not in ["ADMIN", "DG"]:
        raise HTTPException(
            status_code=403,
            detail="Seul l'administrateur ou le DG peut modifier les règles",
        )

    if not check_regle_permission(current_user, "delete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    regle = db.query(RegleAmortissement).filter(RegleAmortissement.id_regle == id_regle).first()
    if not regle:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    
    db.delete(regle)
    db.commit()
    return None

@router.post("/initialiser/defaults", response_model=List[RegleAmortissementResponse])
async def initialiser_regles_default(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_regle_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    regles_default = [
        {
            "categorie_bien": "vehicule",
            "duree_vie_ans": 5,
            "taux_fiscal": 20.0,
            "coeff_deg_3_4_ans": 1.5,
            "coeff_deg_5_6_ans": 2.0,
            "coeff_deg_7_plus_ans": 2.5,
            "compte_dotation": "6812",
            "compte_amortissement": "2845",
            "compte_depreciation": "2944",
            "base_jours_annee": 360,
            "prorata_debut_mois": True,
            "est_active": True
        },
        {
            "categorie_bien": "machine",
            "duree_vie_ans": 10,
            "taux_fiscal": 10.0,
            "coeff_deg_3_4_ans": 1.5,
            "coeff_deg_5_6_ans": 2.0,
            "coeff_deg_7_plus_ans": 2.5,
            "compte_dotation": "6812",
            "compte_amortissement": "2841",
            "compte_depreciation": "2944",
            "base_jours_annee": 360,
            "prorata_debut_mois": True,
            "est_active": True
        },
        {
            "categorie_bien": "ordinateur",
            "duree_vie_ans": 3,
            "taux_fiscal": 33.33,
            "coeff_deg_3_4_ans": 1.5,
            "coeff_deg_5_6_ans": 2.0,
            "coeff_deg_7_plus_ans": 2.5,
            "compte_dotation": "6812",
            "compte_amortissement": "2843",
            "compte_depreciation": "2944",
            "base_jours_annee": 360,
            "prorata_debut_mois": True,
            "est_active": True
        },
        {
            "categorie_bien": "mobilier",
            "duree_vie_ans": 10,
            "taux_fiscal": 10.0,
            "coeff_deg_3_4_ans": 1.5,
            "coeff_deg_5_6_ans": 2.0,
            "coeff_deg_7_plus_ans": 2.5,
            "compte_dotation": "6812",
            "compte_amortissement": "2848",
            "compte_depreciation": "2944",
            "base_jours_annee": 360,
            "prorata_debut_mois": True,
            "est_active": True
        },
        {
            "categorie_bien": "autre",
            "duree_vie_ans": 5,
            "taux_fiscal": 20.0,
            "coeff_deg_3_4_ans": 1.5,
            "coeff_deg_5_6_ans": 2.0,
            "coeff_deg_7_plus_ans": 2.5,
            "compte_dotation": "6812",
            "compte_amortissement": "2840",
            "compte_depreciation": "2944",
            "base_jours_annee": 360,
            "prorata_debut_mois": True,
            "est_active": True
        }
    ]
    
    created_regles = []
    for regle_data in regles_default:
        existing = db.query(RegleAmortissement).filter(
            RegleAmortissement.categorie_bien == regle_data["categorie_bien"]
        ).first()
        
        if not existing:
            regle = RegleAmortissement(
                **regle_data,
                modifie_par=current_user.nom_utilisateur if current_user else "systeme"
            )
            db.add(regle)
            created_regles.append(regle)
    
    db.commit()
    
    for regle in created_regles:
        db.refresh(regle)
    
    return created_regles