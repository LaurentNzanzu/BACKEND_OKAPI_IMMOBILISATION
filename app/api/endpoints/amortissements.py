# backend/app/api/endpoints/amortissements.py
from ast import Dict
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from typing import Any, List, Optional
from datetime import datetime

from ...models.validation import OrdreValidation, TypeValidation, Validation
from ...schemas.cloture import CloturePayload, PrevisualisationClotureResponse
from ...core.database import get_db
from ...schemas.amortissement import AmortissementCreate, AmortissementUpdate, AmortissementResponse, AmortissementListResponse, PlanAmortissementRow, StatistiquesAmortissements
from ...services.amortissement_service import AmortissementService
from ...services.comptabilite_service import ComptabiliteService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.amortissement_workflow_service import AmortissementWorkflowService
from ...schemas.workflow_amortissement import (
    VerifierTresorerieRequest, ValiderDecaissementRequest, ValiderEcritureRequest, WorkflowStatusResponse
)
from ...models.bien import Bien
from ...models.vehicule import Vehicule
from ...models.ordinateur import Ordinateur
from ...models.machine import Machine
from ...models.amortissement import Amortissement

from ...schemas.amortissement import (
    AmortissementValidate, AmortissementVerrouiller, AmortissementVerrouilleResponse,
    AmortissementValidationStatus, AmortissementTresorerieCheck
)
from ...models.amortissement import StatutAmortissement
from ...models.ecriture_comptable import EcritureComptable, StatutEcriture

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/amortissements", tags=["Amortissements"])


# ============================================================
# FONCTION ASYNCHRONE POUR LA CLÔTURE AVANCÉE (BACKGROUND TASK)
# ============================================================

def _cloture_avancee_async(exercice: int, categorie: Optional[str] = None, 
                           methode_forcee: Optional[str] = None,
                           biens_ids: Optional[List[int]] = None):
    """
    Exécute la clôture avancée en arrière-plan.
    Crée sa propre session pour isolation.
    """
    from ...core.database import SessionLocal
    from ...services.amortissement_service import AmortissementService
    
    db = SessionLocal()
    try:
        service = AmortissementService(db)
        resultat = service.generer_amortissements_massifs_avec_filtres(
            exercice=exercice,
            categorie=categorie,
            methode_forcee=methode_forcee,
            biens_ids=biens_ids
        )
        logger.info(
            f"✅ Clôture avancée {exercice} terminée: "
            f"{len(resultat.get('amortissements_crees', []))} amortissements créés"
        )
    except Exception as e:
        logger.error(f"❌ Erreur clôture avancée {exercice}: {e}")
    finally:
        db.close()


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def check_amortissement_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]:
        return True
    if role == "COMPTABLE" and action in ["view", "create", "edit", "verrouiller"]:
        return True
    return action == "view"


def _bien_designation(bien: Bien) -> str:
    label = (
        f"{getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''} "
        f"{getattr(bien, 'modele', '')}"
    ).strip()
    return label or f"Bien #{bien.id_bien}"


def _serialize_amortissement_list(amortissement: Amortissement) -> dict:
    base = AmortissementResponse.model_validate(amortissement).model_dump()
    bien = amortissement.bien
    if bien:
        base.update({
            "qr_code": bien.qr_code,
            "bien_designation": _bien_designation(bien),
            "type_bien": bien.type_bien,
        })
    return base


# ============================================================
# CRÉATION D'AMORTISSEMENT (SYNCHRONE — OPÉRATION UNITAIRE)
# ============================================================

@router.post("", response_model=AmortissementResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=AmortissementResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def calculer_et_enregistrer_amortissement(
    data: AmortissementCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Crée un amortissement pour un bien.
    Opération unitaire, reste synchrone.
    """
    if not check_amortissement_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    logger.info(f"Calcul et enregistrement d'un amortissement pour l'utilisateur {current_user.id}")
    bien = db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
    if not bien:
        raise HTTPException(status_code=404, detail="Bien non trouvé")

    service = AmortissementService(db)
    compt_service = ComptabiliteService(db, cree_par_id=current_user.id)
    audit_service = AuditService(db)

    try:
        amort = service.creer_amortissement(data, bien.type_bien)
        compt_service.generer_ecriture_dotation(amort, bien.type_bien)
        
        # Initialisation automatique du workflow séquentiel en 4 étapes
        try:
            wf_service = AmortissementWorkflowService(db)
            wf_service.initialiser_workflow(amort.id_amortissement, current_user.id)
        except Exception as wf_err:
            logger.warning(f"Erreur lors de l'initialisation du workflow d'amortissement: {wf_err}")

        audit_service.log_create(
            user_id=current_user.id,
            table_name="amortissements",
            record_id=amort.id_amortissement,
            new_values={
                "id_bien": data.id_bien,
                "exercice": data.exercice,
                "methode": data.methode.value if hasattr(data.methode, 'value') else str(data.methode),
                "dotation": float(amort.annuite_comptable) if amort.annuite_comptable else None
            },
            request=request
        )
        
        return amort
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# LECTURE (OPTIMISÉES AVEC JOINEDLOAD)
# ============================================================

@router.get("", response_model=List[AmortissementListResponse])
@router.get("/", response_model=List[AmortissementListResponse], include_in_schema=False)
async def get_all_amortissements(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    categorie: Optional[str] = Query(None, description="Filtrer par catégorie de bien"),
    exercice: Optional[int] = Query(None, description="Filtrer par exercice"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Liste les amortissements avec le bien associé pré-chargé (joinedload).
    ✅ Optimisation N+1
    """
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(Amortissement).options(
        joinedload(Amortissement.bien)
    ).order_by(Amortissement.date_creation.desc())
    
    if categorie:
        query = query.join(Bien).filter(Bien.type_bien == categorie)
    if exercice:
        query = query.filter(Amortissement.exercice == exercice)
    
    amortissements = query.offset(skip).limit(limit).all()
    return [_serialize_amortissement_list(a) for a in amortissements]


@router.get("/bien/{bien_id}", response_model=List[AmortissementResponse])
async def get_historique_amortissements(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère l'historique des amortissements d'un bien."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_historique_par_bien(bien_id)


@router.get("/bien/{bien_id}/depreciations")
async def get_historique_depreciations(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Récupère l'historique des dépréciations d'un bien."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    try:
        return service.get_historique_depreciations(bien_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plan/{bien_id}", response_model=List[PlanAmortissementRow])
async def get_plan_amortissement(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère le plan d'amortissement d'un bien."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_plan_amortissement(bien_id)


@router.get("/statistiques", response_model=StatistiquesAmortissements)
async def get_statistiques_amortissements(
    annee: Optional[int] = Query(None, description="Année pour les statistiques"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les statistiques des amortissements."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_statistiques(annee)


@router.get("/ecarts-fiscaux")
async def get_ecarts_fiscaux(
    annee: int = Query(..., description="Année fiscale"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les écarts fiscaux pour une année."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_ecarts_fiscaux(annee)


@router.get("/composants/{bien_id}")
async def get_amortissement_composants(
    bien_id: int,
    exercice: int = Query(..., description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Calcule l'amortissement par composants pour un bien."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    base_fiscale = service.get_base_fiscale(bien_id)
    return service.calculer_amortissement_composants(bien_id, exercice, base_fiscale)


@router.get("/regles")
async def get_regles_amortissement(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les règles d'amortissement configurées."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_regles_configuration()


# ============================================================
# DÉPRÉCIATION
# ============================================================

@router.post("/{bien_id}/depreciation")
async def appliquer_depreciation(
    bien_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Applique une dépréciation à un bien."""
    if not check_amortissement_permission(current_user, "edit"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    audit_service = AuditService(db)

    try:
        amort = service.appliquer_depreciation(
            bien_id,
            data["nouvelle_valeur"],
            data.get("motif", ""),
            datetime.fromisoformat(data["date_depreciation"])
        )

        compt_service = ComptabiliteService(db, cree_par_id=current_user.id)
        date_dep = datetime.fromisoformat(data["date_depreciation"])
        ecriture = compt_service.generer_ecriture_depreciation(
            amort, float(amort.montant_depreciation), date_dep
        )

        bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if bien:
            bien.statut_comptable = "EN_DEPRECIATION"
            cumul = float(bien.cumul_depreciation or 0) + float(amort.montant_depreciation or 0)
            bien.cumul_depreciation = cumul
            db.commit()
        
        audit_service.log_create(
            user_id=current_user.id,
            table_name="amortissements",
            record_id=amort.id_amortissement,
            new_values={
                "id_bien": bien_id,
                "type": "DEPRECIATION",
                "nouvelle_valeur": data["nouvelle_valeur"],
                "motif": data.get("motif", "")
            },
            request=request
        )
        
        return {
            "message": "Dépréciation appliquée avec succès",
            "amortissement": amort,
            "ecriture": {
                "id_ecriture": ecriture.id_ecriture,
                "compte_debit": ecriture.compte_debit,
                "compte_credit": ecriture.compte_credit,
                "montant": ecriture.montant,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# ÉCRITURES COMPTABLES
# ============================================================

@router.put("/ecritures/{id_ecriture}")
async def update_ecriture_comptable(
    id_ecriture: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Met à jour une écriture comptable (si non validée)."""
    if not check_amortissement_permission(current_user, "edit"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    from ...models.ecriture_comptable import EcritureComptable, StatutEcriture
    
    ecriture = db.query(EcritureComptable).filter(EcritureComptable.id_ecriture == id_ecriture).first()
    if not ecriture:
        raise HTTPException(status_code=404, detail="Écriture non trouvée")
    
    if ecriture.statut not in [StatutEcriture.BROUILLON, StatutEcriture.EN_ATTENTE]:
        raise HTTPException(status_code=400, detail="Impossible de modifier une écriture validée")
    
    audit_service = AuditService(db)
    old_values = {"montant": ecriture.montant, "commentaire": ecriture.commentaire}
    
    if "montant" in data:
        if data["montant"] <= 0:
            raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
        ecriture.montant = float(data["montant"])
    if "commentaire" in data:
        ecriture.commentaire = data["commentaire"]
    
    ecriture.date_modification = datetime.utcnow()
    ecriture.modifie_par = current_user.id
    
    db.commit()
    db.refresh(ecriture)
    
    audit_service.log_update(
        user_id=current_user.id,
        table_name="ecritures_comptables",
        record_id=id_ecriture,
        old_values=old_values,
        new_values={"montant": ecriture.montant, "commentaire": ecriture.commentaire},
        request=request
    )
    
    return ecriture


@router.get("/ecritures/journal-export")
async def get_journal_quotidien(
    date: str = Query(..., description="Date au format YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte le journal quotidien des écritures comptables."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide. Utilisez YYYY-MM-DD")
    
    from ...models.ecriture_comptable import EcritureComptable
    
    ecritures = db.query(EcritureComptable).filter(
        EcritureComptable.type_operation == "AMORTISSEMENT",
        EcritureComptable.date_creation >= date_obj,
        EcritureComptable.date_creation < date_obj.replace(day=date_obj.day+1) if date_obj.day < 28 else None,
        EcritureComptable.statut == "VALIDEE"
    ).order_by(EcritureComptable.numero_piece).all()
    
    return [
        {
            "numero_piece": e.numero_piece,
            "date": e.date_creation.strftime("%Y-%m-%d"),
            "compte_debit": e.compte_debit,
            "compte_credit": e.compte_credit,
            "montant": e.montant,
            "libelle": e.libelle,
            "bien_reference": e.bien_reference if hasattr(e, 'bien_reference') else None
        }
        for e in ecritures
    ]


# ============================================================
# CLÔTURE (AVEC BACKGROUNDTASKS POUR LA CLÔTURE AVANCÉE)
# ============================================================

@router.post("/cloture/{exercice}")
async def cloturer_exercice(
    exercice: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Clôture un exercice (génération des amortissements massifs).
    Opération synchrone — peut être lourde selon le nombre de biens.
    """
    if not check_amortissement_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = AmortissementService(db)
    compt_service = ComptabiliteService(db, cree_par_id=current_user.id)
    result = service.generer_amortissements_massifs(exercice)

    ecritures_generees = []
    for item in result.get("amortissements_crees", []):
        try:
            amort = db.query(Amortissement).filter(
                Amortissement.id_amortissement == item["id_amortissement"]
            ).first()
            bien = db.query(Bien).filter(Bien.id_bien == item["id_bien"]).first()
            if amort and bien:
                ec = compt_service.generer_ecriture_dotation(amort, bien.type_bien or "autre")
                ecritures_generees.append(ec.id_ecriture)
        except Exception as e:
            result.setdefault("erreurs_ecritures", []).append({
                "id_amortissement": item.get("id_amortissement"),
                "erreur": str(e),
            })

    result["ecritures_dotations_generees"] = len(ecritures_generees)
    return result


@router.post("/cloture-avancee")
async def cloturer_exercice_avance(
    payload: CloturePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Clôture avancée avec filtres par catégorie et méthode forcée.
    
    ✅ DÉPORTÉ EN ARRIÈRE-PLAN AVEC BackgroundTasks
    ✅ Retourne immédiatement avec statut 202 Accepted
    """
    if not check_amortissement_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # 🔴 CRITIQUE : Déporter le calcul lourd en arrière-plan
    background_tasks.add_task(
        _cloture_avancee_async,
        exercice=payload.exercice,
        categorie=payload.categorie,
        methode_forcee=payload.methode_forcee.value if payload.methode_forcee else None,
        biens_ids=payload.biens_selectionnes
    )
    
    return {
        "message": f"Clôture avancée pour l'exercice {payload.exercice} en cours",
        "status": "processing",
        "exercice": payload.exercice,
        "categorie": payload.categorie,
        "methode_forcee": payload.methode_forcee,
        "biens_selectionnes": payload.biens_selectionnes
    }


@router.get("/previsualisation-cloture", response_model=PrevisualisationClotureResponse)
async def previsualisation_cloture(
    exercice: int = Query(..., description="Exercice comptable (ex: 2026)"),
    categorie: Optional[str] = Query(None, description="Filtre par catégorie: vehicule, machine, ordinateur"),
    methode_forcee: Optional[str] = Query(None, description="Méthode forcée"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Prévisualise la clôture d'exercice pour les amortissements.
    Lecture rapide, pas de calcul lourd.
    """
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
        
    service = AmortissementService(db)
    
    try:
        resultat = service.previsualiser_cloture(
            exercice=exercice,
            categorie=categorie,
            methode_forcee=methode_forcee
        )
        return resultat
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur prévisualisation clôture: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")


# ============================================================
# TABLEAU DE BORD
# ============================================================

@router.get("/dashboard")
async def get_dashboard_amortissement(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne les indicateurs du tableau de bord des amortissements."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    return service.get_dashboard_data()


@router.get("/comptes")
async def get_plan_comptable(
    classe: Optional[str] = Query(None, description="Filtrer par classe (2,4,5,6,7,8)"),
    type: Optional[str] = Query(None, description="Filtrer par type (actif, passif, charge, produit)"),
    search: Optional[str] = Query(None, description="Recherche par numéro ou libellé"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne la liste des comptes du plan comptable SYSCOHADA."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    from ...models.plan_comptable import PlanComptable
    
    query = db.query(PlanComptable).filter(PlanComptable.est_actif == True)
    
    if classe:
        query = query.filter(PlanComptable.classe == classe)
    if type:
        query = query.filter(PlanComptable.type == type)
    if search:
        query = query.filter(
            (PlanComptable.numero.ilike(f"%{search}%")) |
            (PlanComptable.libelle.ilike(f"%{search}%"))
        )
    
    comptes = query.order_by(PlanComptable.numero).all()
    return [{"id": c.id, "numero": c.numero, "libelle": c.libelle, "classe": c.classe, "type": c.type} for c in comptes]


# ============================================================
# VALIDATION ET VERROUILLAGE DES AMORTISSEMENTS
# ============================================================

def _get_details_specifiques(bien: Bien) -> dict[str, Any]:
    """
    Récupère les attributs spécifiques selon le type de bien.
    """
    details = {}
    
    if bien.type_bien == "vehicule" or isinstance(bien, Vehicule):
        details = {
            "type": "Vehicule",
            "marque": getattr(bien, 'marque', None),
            "modele": getattr(bien, 'modele', None),
            "immatriculation": getattr(bien, 'immatriculation', None),
            "type_vehicule": getattr(bien, 'type_vehicule', None),
            "type_carburant": getattr(bien, 'type_carburant', None),
            "consommation_carburant": getattr(bien, 'consommation_carburant', None)
        }
    
    elif bien.type_bien == "ordinateur" or isinstance(bien, Ordinateur):
        details = {
            "type": "Ordinateur",
            "marque": getattr(bien, 'marque', None),
            "modele": getattr(bien, 'modele', None),
            "processeur": getattr(bien, 'processeur', None),
            "ram": getattr(bien, 'ram', None),
            "stockage": getattr(bien, 'stockage', None),
            "adresse_ip": getattr(bien, 'adresse_ip', None),
            "utilisateur_affecte": getattr(bien, 'utilisateur_affecte', None)
        }
    
    elif bien.type_bien == "machine" or isinstance(bien, Machine):
        details = {
            "type": "Machine",
            "fabricant": getattr(bien, 'fabricant', None),
            "modele": getattr(bien, 'modele', None),
            "numero_serie": getattr(bien, 'numero_serie', None),
            "puissance": getattr(bien, 'puissance', None),
            "type_alimentation": getattr(bien, 'type_alimentation', None),
            "service_affecte": getattr(bien, 'service_affecte', None),
            "responsable": getattr(bien, 'responsable', None)
        }
    else:
        details = {"type": "Bien générique"}
    
    return {k: v for k, v in details.items() if v is not None}


@router.post("/{id_amortissement}/valider", response_model=dict)
async def valider_amortissement(
    id_amortissement: int,
    data: AmortissementValidate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Valide un amortissement.
    - Vérifie la trésorerie disponible
    - Génère les écritures comptables SYSCOHADA
    - Verrouille le tableau d'amortissement
    """
    if not check_amortissement_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    audit_service = AuditService(db)
    
    amortissement = db.query(Amortissement).filter(
        Amortissement.id_amortissement == id_amortissement
    ).first()
    
    if not amortissement:
        raise HTTPException(status_code=404, detail="Amortissement non trouvé")
    
    if amortissement.est_verrouille:
        raise HTTPException(status_code=400, detail="Cet amortissement est déjà verrouillé")
    
    try:
        if not data.valide:
            amortissement.statut = StatutAmortissement.SUSPENDU
            
            audit_service.log_action(
                user_id=current_user.id,
                table_name="amortissements",
                record_id=id_amortissement,
                action="AMORTISSEMENT_INVALIDE",
                nouvelles_valeurs={
                    "motif": data.motif,
                    "statut": amortissement.statut.value
                },
                request=request
            )
            
            db.commit()
            
            return {
                "id_amortissement": id_amortissement,
                "statut": amortissement.statut.value,
                "message": "Amortissement invalidé",
                "motif": data.motif
            }
        
        # Validation avec vérification de trésorerie
        resultat = service.traiter_amortissement_apres_cloture(id_amortissement, current_user.id)
        
        audit_service.log_action(
            user_id=current_user.id,
            table_name="amortissements",
            record_id=id_amortissement,
            action="AMORTISSEMENT_VALIDE",
            nouvelles_valeurs={
                "statut": amortissement.statut.value,
                "verrouille": amortissement.est_verrouille
            },
            request=request
        )
        
        return resultat
        
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{id_amortissement}/verrouillage", response_model=AmortissementVerrouilleResponse)
async def get_verrouillage_amortissement(
    id_amortissement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Vérifie si un amortissement est verrouillé."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    amortissement = db.query(Amortissement).filter(
        Amortissement.id_amortissement == id_amortissement
    ).first()
    
    if not amortissement:
        raise HTTPException(status_code=404, detail="Amortissement non trouvé")
    
    validateur_nom = None
    if amortissement.verrouille_par:
        validateur = db.query(Utilisateur).filter(
            Utilisateur.id == amortissement.verrouille_par
        ).first()
        if validateur:
            validateur_nom = validateur.nom
    
    return AmortissementVerrouilleResponse(
        id_amortissement=amortissement.id_amortissement,
        id_bien=amortissement.id_bien,
        exercice=amortissement.exercice,
        est_verrouille=amortissement.est_verrouille or False,
        date_verrouillage=amortissement.date_verrouillage,
        verrouille_par=amortissement.verrouille_par,
        verrouille_par_nom=validateur_nom,
        raison_verrouillage="Validation définitive après clôture",
        est_modifiable=not (amortissement.est_verrouille or False)
    )


@router.get("/verrouilles", response_model=List[AmortissementVerrouilleResponse])
async def get_amortissements_verrouilles(
    exercice: Optional[int] = Query(None, description="Filtrer par exercice"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère la liste des amortissements verrouillés."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(Amortissement).filter(Amortissement.est_verrouille == True)
    
    if exercice:
        query = query.filter(Amortissement.exercice == exercice)
    
    amortissements = query.all()
    
    resultats = []
    for amort in amortissements:
        validateur_nom = None
        if amort.verrouille_par:
            validateur = db.query(Utilisateur).filter(
                Utilisateur.id == amort.verrouille_par
            ).first()
            if validateur:
                validateur_nom = validateur.nom
        
        resultats.append(AmortissementVerrouilleResponse(
            id_amortissement=amort.id_amortissement,
            id_bien=amort.id_bien,
            exercice=amort.exercice,
            est_verrouille=True,
            date_verrouillage=amort.date_verrouillage,
            verrouille_par=amort.verrouille_par,
            verrouille_par_nom=validateur_nom,
            raison_verrouillage="Validation définitive après clôture",
            est_modifiable=False
        ))
    
    return resultats


@router.get("/{id_amortissement}/validation-status", response_model=AmortissementValidationStatus)
async def get_validation_status_amortissement(
    id_amortissement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère le statut de validation d'un amortissement."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    amortissement = db.query(Amortissement).filter(
        Amortissement.id_amortissement == id_amortissement
    ).first()
    
    if not amortissement:
        raise HTTPException(status_code=404, detail="Amortissement non trouvé")
    
    validations = db.query(Validation).filter(
        Validation.id_bien == amortissement.id_bien,
        Validation.type_validation == TypeValidation.AMORTISSEMENT
    ).all()
    
    ecritures = db.query(EcritureComptable).filter(
        EcritureComptable.id_amortissement == id_amortissement
    ).all()
    
    service = AmortissementService(db)
    tresorerie = service.calculer_et_verifier_tresorerie(id_amortissement)
    
    return AmortissementValidationStatus(
        id_amortissement=id_amortissement,
        statut_validation="VALIDE" if amortissement.est_verrouille else "EN_ATTENTE",
        validations=[
            {
                "id_validation": v.id_validation,
                "ordre": v.ordre_validateur.value,
                "decision": v.decision.value,
                "date": v.date_validation.isoformat() if v.date_validation else None
            }
            for v in validations
        ],
        ecritures_generees=[
            {
                "id_ecriture": e.id_ecriture,
                "type": e.type_operation.value,
                "montant": float(e.montant),
                "statut": e.statut.value
            }
            for e in ecritures
        ],
        montant_total_dotations=float(amortissement.annuite_comptable or 0),
        besoins_tresorerie=float(amortissement.annuite_comptable or 0),
        tresorerie_disponible=tresorerie["tresorerie_disponible"],
        validation_caissier=next((v for v in validations if v.ordre_validateur == OrdreValidation.CAISSE), None),
        validation_dg=next((v for v in validations if v.ordre_validateur == OrdreValidation.DG), None)
    )


@router.get("/{id_amortissement}/tresorerie", response_model=AmortissementTresorerieCheck)
async def check_tresorerie_amortissement(
    id_amortissement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Vérifie la trésorerie pour un amortissement."""
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    
    try:
        resultat = service.calculer_et_verifier_tresorerie(id_amortissement)
        return resultat
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/cloture/previsualisation-detaille")
async def previsualisation_cloture_detaille(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Prévisualisation détaillée de la clôture avec biens filtrés.
    """
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    exercice = payload.get("exercice")
    if not exercice:
        raise HTTPException(status_code=400, detail="L'exercice est requis")
    
    service = AmortissementService(db)
    
    try:
        resultat = service.previsualiser_cloture(
            exercice=exercice,
            categorie=payload.get("categorie"),
            methode_forcee=payload.get("methode_forcee"),
            biens_ids=payload.get("biens_ids")
        )
        return resultat
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{amortissement_id}/verrouiller", response_model=AmortissementVerrouilleResponse)
async def verrouiller_amortissement_endpoint(
    amortissement_id: int,
    data: AmortissementVerrouiller,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Verrouille définitivement un amortissement.
    🔒 Une fois verrouillé, l'amortissement ne peut plus être modifié.
    ⚠️ Seul le DG, le Comptable ou l'Admin peut effectuer cette opération.
    """
    if not check_amortissement_permission(current_user, "verrouiller"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = AmortissementService(db)
    
    try:
        amortissement = service.verrouiller_amortissement(
            id_amortissement=amortissement_id,
            verrouille_par=current_user.id,
            raison=data.raison
        )
        
        nom_user = current_user.nom if hasattr(current_user, 'nom') else str(current_user.id)
        return AmortissementVerrouilleResponse(
            id_amortissement=amortissement.id_amortissement,
            id_bien=amortissement.id_bien,
            exercice=amortissement.exercice,
            est_verrouille=amortissement.est_verrouille,
            date_verrouillage=amortissement.date_verrouillage,
            verrouille_par_id=current_user.id,
            verrouille_par_nom=nom_user,
            raison_verrouillage=amortissement.raison_verrouillage,
            est_modifiable=False
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD verrouillage amortissement: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


# ============================================================
# ENDPOINTS WORKFLOW DE VALIDATION EN 4 ÉTAPES
# ============================================================

@router.get("/{id_amortissement}/workflow-status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    id_amortissement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère le statut détaillé et l'historique du workflow de validation pour un amortissement."""
    service = AmortissementWorkflowService(db)
    return service.get_workflow_status(id_amortissement)


@router.post("/{id_amortissement}/verifier-tresorerie")
async def verifier_tresorerie_caisse(
    id_amortissement: int,
    data: VerifierTresorerieRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Étape 2: La CAISSE vérifie la disponibilité physique des fonds en trésorerie."""
    service = AmortissementWorkflowService(db)
    try:
        res = service.verifier_tresorerie(
            id_amortissement=id_amortissement,
            tresorerie_disponible=data.tresorerie_disponible,
            commentaire=data.commentaire or "",
            user_id=current_user.id
        )
        db.commit()
        return {"success": True, "statut": res.statut.value, "etape": res.etape.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{id_amortissement}/valider-decaissement")
async def valider_decaissement_dg(
    id_amortissement: int,
    data: ValiderDecaissementRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Étape 3: Le DG valide le décaissement et déclenche la génération du Bon de Décaissement PDF."""
    service = AmortissementWorkflowService(db)
    try:
        res = service.valider_decaissement(
            id_amortissement=id_amortissement,
            approuve=data.approuve,
            motif=data.motif or "",
            user_id=current_user.id
        )
        db.commit()
        return {
            "success": True,
            "statut": res.statut.value,
            "etape": res.etape.value,
            "bon_decaissement_pdf": res.bon_decaissement_pdf
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{id_amortissement}/valider-ecriture")
async def valider_ecriture_comptable(
    id_amortissement: int,
    data: ValiderEcritureRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Étape 4: Le COMPTABLE effectue la validation finale de l'écriture et verrouille l'amortissement."""
    service = AmortissementWorkflowService(db)
    try:
        res = service.valider_ecriture(
            id_amortissement=id_amortissement,
            piece_justificative_url=data.piece_justificative_url,
            commentaire=data.commentaire,
            user_id=current_user.id
        )
        db.commit()
        return {"success": True, "statut": res.statut.value, "etape": res.etape.value, "est_verrouille": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{id_amortissement}/bon-decaissement-pdf")
async def telecharger_bon_decaissement_pdf(
    id_amortissement: int,
    db: Session = Depends(get_db)
):
    """Téléchargement direct du Bon de Décaissement PDF pour l'amortissement donné."""
    import os
    service = AmortissementWorkflowService(db)
    status_data = service.get_workflow_status(id_amortissement)
    dg_step = next((h for h in status_data.get("historique_validations", []) if h.get("etape") == "DG"), None)
    
    pdf_rel_path = dg_step.get("bon_decaissement_pdf") if dg_step else None
    if not pdf_rel_path:
        raise HTTPException(status_code=404, detail="Bon de décaissement non encore généré pour cet amortissement.")
    
    # Supprimer les slashs initiaux pour obtenir le chemin fichier local
    clean_path = pdf_rel_path.lstrip('/')
    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail="Fichier PDF non trouvé sur le serveur.")
        
    return FileResponse(
        clean_path, 
        media_type="application/pdf", 
        filename=f"bon_decaissement_amortissement_{id_amortissement}.pdf"
    )
