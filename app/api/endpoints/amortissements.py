# backend/app/api/endpoints/amortissements.py
from ast import Dict
import logging

from fastapi import APIRouter, Depends, HTTPException,  status, Query, Request
from sqlalchemy.orm import Session, joinedload
from typing import Any, List, Optional
from datetime import datetime
from ...schemas.cloture import CloturePayload, PrevisualisationClotureResponse
from ...core.database import get_db
from ...schemas.amortissement import AmortissementCreate, AmortissementUpdate, AmortissementResponse, AmortissementListResponse, PlanAmortissementRow, StatistiquesAmortissements
from ...services.amortissement_service import AmortissementService
from ...services.comptabilite_service import ComptabiliteService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...models.vehicule import Vehicule
from ...models.ordinateur import Ordinateur
from ...models.machine import Machine
from ...models.amortissement import Amortissement

router = APIRouter(prefix="/amortissements", tags=["Amortissements"])

logger = logging.getLogger(__name__)

def check_amortissement_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]:
        return True
    if role == "COMPTABLE" and action in ["view", "create", "edit"]:
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


@router.post("", response_model=AmortissementResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=AmortissementResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def calculer_et_enregistrer_amortissement(
    data: AmortissementCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
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
        
        # Enregistrer l'audit
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


@router.get("/bien/{bien_id}", response_model=List[AmortissementResponse])
async def get_historique_amortissements(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
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
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_ecarts_fiscaux(annee)


@router.get("", response_model=List[AmortissementListResponse])
@router.get("/", response_model=List[AmortissementListResponse], include_in_schema=False)
async def get_all_amortissements(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    categorie: Optional[str] = Query(None, description="Filtrer par catégorie de bien"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(Amortissement).options(
        joinedload(Amortissement.bien)
    ).order_by(Amortissement.date_creation.desc())
    
    if categorie:
        query = query.join(Bien).filter(Bien.type_bien == categorie)
    
    amortissements = query.offset(skip).limit(limit).all()
    return [_serialize_amortissement_list(a) for a in amortissements]


@router.get("/composants/{bien_id}")
async def get_amortissement_composants(
    bien_id: int,
    exercice: int = Query(..., description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    base_fiscale = service.get_base_fiscale(bien_id)
    return service.calculer_amortissement_composants(bien_id, exercice, base_fiscale)


@router.post("/{bien_id}/depreciation")
async def appliquer_depreciation(
    bien_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
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
        
        # Enregistrer l'audit
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


@router.put("/ecritures/{id_ecriture}")
async def update_ecriture_comptable(
    id_ecriture: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
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
        ecriture.montant = float(data["montant"])
    if "commentaire" in data:
        ecriture.commentaire = data["commentaire"]
    
    ecriture.date_modification = datetime.utcnow()
    ecriture.modifie_par = current_user.id
    
    db.commit()
    db.refresh(ecriture)
    
    # Enregistrer l'audit
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


@router.post("/cloture/{exercice}")
async def cloturer_exercice(
    exercice: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
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


@router.get("/regles")
async def get_regles_amortissement(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = AmortissementService(db)
    return service.get_regles_configuration()


@router.post("/cloture-avancee")
async def cloturer_exercice_avance(
    payload: CloturePayload,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Clôture avancée avec filtres par catégorie et méthode forcée.
    """
    if not check_amortissement_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = AmortissementService(db)
    compt_service = ComptabiliteService(db, cree_par_id=current_user.id)
    audit_service = AuditService(db)

    try:
        # Générer les amortissements avec filtres
        result = service.generer_amortissements_massifs_avec_filtres(
            exercice=payload.exercice,
            categorie=payload.categorie,
            methode_forcee=payload.methode_forcee.value if payload.methode_forcee else None,
            biens_ids=payload.biens_selectionnes
        )

        # Générer les écritures comptables pour chaque amortissement créé
        ecritures_generees = []
        for item in result.get("amortissements_crees", []):
            try:
                amort = db.query(Amortissement).filter(
                    Amortissement.id_amortissement == item["id_amortissement"]
                ).first()
                bien = db.query(Bien).filter(Bien.id_bien == item["id_bien"]).first()
                if amort and bien:
                    ec = compt_service.generer_ecriture_dotation(amort, bien.type_bien or "autre")
                    ecritures_generees.append({
                        "id_ecriture": ec.id_ecriture,
                        "id_amortissement": amort.id_amortissement,
                        "id_bien": bien.id_bien,
                        "montant": ec.montant
                    })
                    
                    # Audit de l'écriture
                    audit_service.log_create(
                        user_id=current_user.id,
                        table_name="ecritures_comptables",
                        record_id=ec.id_ecriture,
                        new_values={
                            "id_bien": bien.id_bien,
                            "type": "DOTATION_AMORTISSEMENT",
                            "montant": ec.montant,
                            "exercice": payload.exercice
                        },
                        request=request
                    )
            except Exception as e:
                result.setdefault("erreurs_ecritures", []).append({
                    "id_amortissement": item.get("id_amortissement"),
                    "id_bien": item.get("id_bien"),
                    "erreur": str(e),
                })

        result["ecritures_dotations_generees"] = len(ecritures_generees)
        result["date_execution"] = datetime.utcnow().isoformat()
        
        return result

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/previsualisation-cloture", response_model=PrevisualisationClotureResponse)
async def previsualisation_cloture(
    exercice: int = Query(..., description="Exercice comptable (ex: 2026)"),
    categorie: Optional[str] = Query(None, description="Filtre par catégorie: vehicule, machine, ordinateur"),
    methode_forcee: Optional[str] = Query(None, description="Méthode forcée"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Prévisualise la clôture d'exercice pour les amortissements via le Service centralisé.
    """
    if not check_amortissement_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
        
    service = AmortissementService(db)
    
    try:
        # Appel de la méthode robuste de ton service
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
    """Retourne la liste des comptes du plan comptable."""
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


def _get_details_specifiques(bien: Bien) -> dict[str, Any]:
    """
    Récupère les attributs spécifiques selon le type de bien.
    Utilise le polymorphisme SQLAlchemy pour détecter la classe réelle.
    """
    details = {}
    
    # Vérifier le type via polymorphic_identity et isinstance
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
    
    # Filtrer les valeurs None pour alléger la réponse
    return {k: v for k, v in details.items() if v is not None}