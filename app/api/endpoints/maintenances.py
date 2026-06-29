# backend/app/api/endpoints/maintenances.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from typing import List, Optional
from datetime import datetime
from ...core.database import get_db
from ...schemas.maintenance import (
    MaintenanceCreate, MaintenanceUpdate, MaintenanceResponse,
    MaintenanceListResponse, MaintenanceReporter, MaintenanceTerminer,
    MaintenanceStatistics
)
from ...services.maintenance_service import MaintenanceService
from ...services.audit_service import AuditService
from ...services.notification_service import NotificationService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import Bien
from ...models.maintenance import Maintenance, TypeMaintenance, StatutMaintenance, TypeOrigineMaintenance
from ...models.notification import TypeNotificationEnum

router = APIRouter(prefix="/maintenances", tags=["Maintenances"])

def check_maintenance_permission(user: Utilisateur, action: str) -> bool:
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG"]:
        return True
    if role == "COMPTABLE" and action == "view":
        return True
    if role == "TECHNICIEN" and action in ["view", "create", "update", "start", "complete", "report"]:
        return True
    return action == "view"


@router.post("/", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
async def planifier_maintenance(
    data: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_maintenance_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MaintenanceService(db)
    audit_service = AuditService(db)
    
    try:
        maintenance = service.planifier_maintenance(data, current_user.id)
        
        # Enregistrer l'audit
        audit_service.log_create(
            user_id=current_user.id,
            table_name="maintenances",
            record_id=maintenance.id_maintenance,
            new_values={
                "id_bien": data.id_bien,
                "type_maintenance": data.type_maintenance.value if hasattr(data.type_maintenance, 'value') else str(data.type_maintenance),
                "date_planifiee": str(data.date_planifiee),
                "description": data.description
            },
            request=request
        )
        
        return maintenance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bien/{bien_id}", response_model=List[MaintenanceResponse])
async def get_maintenances_by_bien(
    bien_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    return service.get_maintenances_by_bien(bien_id, skip, limit)


@router.get("/panne/{panne_id}", response_model=List[MaintenanceResponse])
async def get_maintenances_by_panne(
    panne_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    return service.get_maintenances_by_panne(panne_id)


@router.get("/mes-maintenances", response_model=List[MaintenanceResponse])
async def get_mes_maintenances(
    statut: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if current_user.role.nom.upper() != "TECHNICIEN":
        raise HTTPException(status_code=403, detail="Seul un technicien peut voir ses maintenances")
    service = MaintenanceService(db)
    return service.get_maintenances_by_technicien(current_user.id, statut)


@router.get("/a-venir", response_model=List[MaintenanceResponse])
async def get_maintenances_a_venir(
    jours: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    return service.get_maintenances_a_venir(jours)


@router.get("/en-retard", response_model=List[MaintenanceResponse])
async def get_maintenances_en_retard(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    return service.get_maintenances_en_retard()


@router.get("/{maintenance_id}", response_model=MaintenanceResponse)
async def get_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    maintenance = service.get_maintenance(maintenance_id)
    if not maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    return maintenance


@router.put("/{maintenance_id}", response_model=MaintenanceResponse)
async def update_maintenance(
    maintenance_id: int,
    data: MaintenanceUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_maintenance_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MaintenanceService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancienne maintenance
    old_maintenance = service.get_maintenance(maintenance_id)
    if not old_maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    maintenance = service.update_maintenance(maintenance_id, data)
    if not maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    # Enregistrer l'audit
    audit_service.log_update(
        user_id=current_user.id,
        table_name="maintenances",
        record_id=maintenance_id,
        old_values={
            "date_planifiee": str(old_maintenance.date_planifiee) if old_maintenance.date_planifiee else None,
            "description": old_maintenance.description
        },
        new_values={
            "date_planifiee": str(maintenance.date_planifiee) if maintenance.date_planifiee else None,
            "description": maintenance.description
        },
        request=request
    )
    
    return maintenance


@router.post("/{maintenance_id}/demarrer", response_model=MaintenanceResponse)
async def demarrer_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_maintenance_permission(current_user, "start"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MaintenanceService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancien statut
    old_maintenance = service.get_maintenance(maintenance_id)
    if not old_maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    try:
        maintenance = service.demarrer_maintenance(maintenance_id)
        if not maintenance:
            raise HTTPException(status_code=404, detail="Maintenance non trouvée")
        
        # Enregistrer l'audit
        audit_service.log_update(
            user_id=current_user.id,
            table_name="maintenances",
            record_id=maintenance_id,
            old_values={"statut": old_maintenance.statut.value if old_maintenance.statut else None},
            new_values={"statut": maintenance.statut.value if maintenance.statut else None},
            request=request
        )
        
        return maintenance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{maintenance_id}/terminer", response_model=MaintenanceResponse)
async def terminer_maintenance(
    maintenance_id: int,
    data: MaintenanceTerminer,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_maintenance_permission(current_user, "complete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MaintenanceService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancienne maintenance
    old_maintenance = service.get_maintenance(maintenance_id)
    if not old_maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    try:
        maintenance = service.terminer_maintenance(
            maintenance_id,
            data.rapport,
            data.cout,
            data.pieces_remplacees
        )
        if not maintenance:
            raise HTTPException(status_code=404, detail="Maintenance non trouvée")
        
        # Enregistrer l'audit
        audit_service.log_update(
            user_id=current_user.id,
            table_name="maintenances",
            record_id=maintenance_id,
            old_values={
                "statut": old_maintenance.statut.value if old_maintenance.statut else None,
                "cout": old_maintenance.cout
            },
            new_values={
                "statut": maintenance.statut.value if maintenance.statut else None,
                "cout": data.cout,
                "rapport": data.rapport
            },
            request=request
        )
        
        return maintenance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{maintenance_id}/reporter", response_model=MaintenanceResponse)
async def reporter_maintenance(
    maintenance_id: int,
    data: MaintenanceReporter,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_maintenance_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MaintenanceService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancienne maintenance
    old_maintenance = service.get_maintenance(maintenance_id)
    if not old_maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    try:
        maintenance = service.reporter_maintenance(maintenance_id, data.nouvelle_date, data.motif)
        if not maintenance:
            raise HTTPException(status_code=404, detail="Maintenance non trouvée")
        
        # Enregistrer l'audit
        audit_service.log_update(
            user_id=current_user.id,
            table_name="maintenances",
            record_id=maintenance_id,
            old_values={"date_planifiee": str(old_maintenance.date_planifiee) if old_maintenance.date_planifiee else None},
            new_values={"date_planifiee": str(data.nouvelle_date), "motif_report": data.motif},
            request=request
        )
        
        return maintenance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{maintenance_id}/annuler", response_model=MaintenanceResponse)
async def annuler_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    if not check_maintenance_permission(current_user, "update"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = MaintenanceService(db)
    audit_service = AuditService(db)
    
    # Récupérer l'ancien statut
    old_maintenance = service.get_maintenance(maintenance_id)
    if not old_maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    try:
        maintenance = service.annuler_maintenance(maintenance_id)
        if not maintenance:
            raise HTTPException(status_code=404, detail="Maintenance non trouvée")
        
        # Enregistrer l'audit
        audit_service.log_update(
            user_id=current_user.id,
            table_name="maintenances",
            record_id=maintenance_id,
            old_values={"statut": old_maintenance.statut.value if old_maintenance.statut else None},
            new_values={"statut": maintenance.statut.value if maintenance.statut else None},
            request=request
        )
        
        return maintenance
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/statistiques/summary", response_model=MaintenanceStatistics)
async def get_maintenance_statistiques(
    annee: Optional[int] = Query(None, description="Année pour les statistiques"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    stats = service.get_statistiques(annee)
    return MaintenanceStatistics(
        total_maintenances=stats["total_maintenances"],
        par_type=stats["par_type"],
        par_statut=stats["par_statut"],
        cout_total_annee=stats["cout_total_annee"],
        cout_moyen=stats["cout_moyen"],
        taux_realisation=stats["taux_realisation"],
        alertes=stats["alertes"]
    )


@router.get("/bien/{bien_id}/duree-vie")
async def get_bien_duree_vie(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MaintenanceService(db)
    result = service.calculer_duree_vie_bien(bien_id)
    if not result:
        raise HTTPException(status_code=404, detail="Bien non trouvé")
    return result


# ============================================================
# NOUVEAUX ENDPOINTS TÂCHE 3 - ALERTES MAINTENANCE
# ============================================================

@router.get("/alertes")
async def get_alertes_maintenance(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère toutes les alertes de maintenance
    - Biens critiques sous surveillance (tri par SF croissant)
    - Maintenances préventives auto-générées
    """
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    # 1. Biens critiques avec leur score
    biens_critiques = db.query(Bien).filter(
        Bien.est_critique == True,
        Bien.statut_comptable == 'ACTIF'
    ).order_by(Bien.score_fiabilite.asc()).all()
    
    # 2. Maintenances préventives auto-générées en attente
    maintenances_auto = db.query(Maintenance).filter(
        Maintenance.origine == TypeOrigineMaintenance.AUTO,
        Maintenance.statut == StatutMaintenance.PLANIFIEE
    ).order_by(Maintenance.date_planifiee.asc()).all()
    
    # 3. Enrichir avec les couleurs
    resultat = {
        "biens_critiques": [
            {
                "id": b.id_bien,
                "designation": b.description or f"Bien #{b.id_bien}",
                "score_fiabilite": b.score_fiabilite,
                "est_critique": b.est_critique,
                "couleur": "vert" if b.score_fiabilite >= 60 else 
                           "orange" if b.score_fiabilite >= 30 else "rouge",
                "seuil": "Critique" if b.score_fiabilite < 30 else "Moyen" if b.score_fiabilite < 60 else "Bon"
            }
            for b in biens_critiques
        ],
        "maintenances_auto": [
            {
                "id": m.id_maintenance,
                "bien_id": m.id_bien,
                "bien_designation": m.bien.description if m.bien else f"Bien #{m.id_bien}",
                "date_planifiee": m.date_planifiee,
                "score_fiabilite_depart": m.score_fiabilite_depart,
                "statut": m.statut.value if m.statut else None
            }
            for m in maintenances_auto
        ],
        "total_biens_critiques": len(biens_critiques),
        "total_maintenances_auto": len(maintenances_auto),
        "seuils": {
            "critique": 30,
            "moyen": 60,
            "bon": 100
        }
    }
    
    return resultat


@router.post("/{maintenance_id}/executer")
async def executer_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Marque une maintenance comme exécutée"""
    if not check_maintenance_permission(current_user, "complete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    maintenance = db.query(Maintenance).filter(
        Maintenance.id_maintenance == maintenance_id
    ).first()
    
    if not maintenance:
        raise HTTPException(status_code=404, detail="Maintenance non trouvée")
    
    if maintenance.statut != StatutMaintenance.PLANIFIEE:
        raise HTTPException(
            status_code=400, 
            detail=f"Impossible d'exécuter une maintenance en statut {maintenance.statut.value}"
        )
    
    # Marquer comme exécutée
    maintenance.statut = StatutMaintenance.TERMINEE
    maintenance.date_debut_reelle = datetime.utcnow()
    maintenance.date_fin_reelle = datetime.utcnow()
    
    db.commit()
    db.refresh(maintenance)
    
    # Journaliser l'audit
    audit_service = AuditService(db)
    audit_service.log_update(
        user_id=current_user.id,
        table_name="maintenances",
        record_id=maintenance_id,
        old_values={"statut": "PLANIFIEE"},
        new_values={"statut": "TERMINEE"}
    )
    
    # Envoyer une notification
    notification_service = NotificationService(db)
    bien = db.query(Bien).filter(Bien.id_bien == maintenance.id_bien).first()
    designation = bien.description if bien else f"Bien #{maintenance.id_bien}"
    
    notification_service.envoyer_notification_par_role(
        role_nom="DG",
        type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
        titre=f"✅ Maintenance exécutée - {designation}",
        contenu=f"La maintenance préventive sur le bien {designation} a été marquée comme exécutée.",
        lien=f"/maintenances/{maintenance_id}"
    )
    
    return {"message": "Maintenance exécutée avec succès", "id": maintenance_id}


@router.get("/auto-generees", response_model=List[dict])
async def get_maintenances_auto_generees(
    statut: Optional[str] = Query(None, description="Filtrer par statut"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère toutes les maintenances auto-générées
    """
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(Maintenance).filter(
        Maintenance.origine == TypeOrigineMaintenance.AUTO
    )
    
    if statut:
        try:
            statut_enum = StatutMaintenance(statut.upper())
            query = query.filter(Maintenance.statut == statut_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Statut invalide: {statut}")
    
    maintenances = query.order_by(Maintenance.date_creation.desc()).all()
    
    return [
        {
            "id": m.id_maintenance,
            "bien_id": m.id_bien,
            "bien_designation": m.bien.description if m.bien else f"Bien #{m.id_bien}",
            "type_maintenance": m.type_maintenance.value if m.type_maintenance else None,
            "statut": m.statut.value if m.statut else None,
            "date_planifiee": m.date_planifiee,
            "score_fiabilite_depart": m.score_fiabilite_depart,
            "date_creation": m.date_creation,
            "est_en_retard": m.est_en_retard,
            "jours_restants": m.jours_restants_avant_maintenance() if m.statut == StatutMaintenance.PLANIFIEE else 0
        }
        for m in maintenances
    ]


@router.get("/statistiques/auto-generees")
async def get_statistiques_auto_generees(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Statistiques sur les maintenances auto-générées
    """
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    # Total auto-générées
    total_auto = db.query(Maintenance).filter(
        Maintenance.origine == TypeOrigineMaintenance.AUTO
    ).count()
    
    # Par statut
    par_statut = {}
    for statut in StatutMaintenance:
        count = db.query(Maintenance).filter(
            Maintenance.origine == TypeOrigineMaintenance.AUTO,
            Maintenance.statut == statut
        ).count()
        if count > 0:
            par_statut[statut.value] = count
    
    # Score moyen de départ
    avg_score = db.query(func.avg(Maintenance.score_fiabilite_depart)).filter(
        Maintenance.origine == TypeOrigineMaintenance.AUTO,
        Maintenance.score_fiabilite_depart.isnot(None)
    ).scalar() or 0
    
    # Taux de réalisation
    terminees = db.query(Maintenance).filter(
        Maintenance.origine == TypeOrigineMaintenance.AUTO,
        Maintenance.statut == StatutMaintenance.TERMINEE
    ).count()
    
    taux_realisation = round((terminees / total_auto * 100), 1) if total_auto > 0 else 0
    
    return {
        "total_auto_generees": total_auto,
        "par_statut": par_statut,
        "score_moyen_depart": round(float(avg_score), 2),
        "taux_realisation": taux_realisation,
        "terminees": terminees,
        "en_attente": par_statut.get(StatutMaintenance.PLANIFIEE.value, 0),
        "en_cours": par_statut.get(StatutMaintenance.EN_COURS.value, 0)
    }


@router.post("/{maintenance_id}/executer-auto")
async def executer_maintenance_auto(
    maintenance_id: int,
    observations: Optional[str] = Query(None, description="Observations sur l'exécution"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Exécute une maintenance auto-générée
    """
    if not check_maintenance_permission(current_user, "complete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    maintenance = db.query(Maintenance).filter(
        Maintenance.id_maintenance == maintenance_id,
        Maintenance.origine == TypeOrigineMaintenance.AUTO
    ).first()
    
    if not maintenance:
        raise HTTPException(status_code=404, detail="Maintenance auto-générée non trouvée")
    
    if maintenance.statut != StatutMaintenance.PLANIFIEE:
        raise HTTPException(
            status_code=400, 
            detail=f"Impossible d'exécuter une maintenance en statut {maintenance.statut.value}"
        )
    
    # Marquer comme exécutée
    maintenance.statut = StatutMaintenance.TERMINEE
    maintenance.date_debut_reelle = datetime.utcnow()
    maintenance.date_fin_reelle = datetime.utcnow()
    if observations:
        maintenance.observation = (maintenance.observation or "") + f"\nExécution auto: {observations}"
    
    db.commit()
    db.refresh(maintenance)
    
    # Journaliser l'audit
    audit_service = AuditService(db)
    audit_service.log_update(
        user_id=current_user.id,
        table_name="maintenances",
        record_id=maintenance_id,
        old_values={"statut": "PLANIFIEE"},
        new_values={"statut": "TERMINEE", "origine": "AUTO"}
    )
    
    # Envoyer une notification au DG
    notification_service = NotificationService(db)
    bien = db.query(Bien).filter(Bien.id_bien == maintenance.id_bien).first()
    designation = bien.description if bien else f"Bien #{maintenance.id_bien}"
    
    notification_service.envoyer_notification_par_role(
        role_nom="DG",
        type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
        titre=f"✅ Maintenance auto exécutée - {designation}",
        contenu=f"La maintenance préventive auto-générée sur le bien {designation} a été exécutée.",
        lien=f"/maintenances/{maintenance_id}"
    )
    
    return {
        "message": "Maintenance auto-générée exécutée avec succès", 
        "id": maintenance_id,
        "bien_id": maintenance.id_bien,
        "score_depart": maintenance.score_fiabilite_depart
    }


@router.get("/alerte-vnc/ordres")
async def get_ordres_remplacement(
    statut: Optional[str] = Query(None, description="Filtrer par statut"),
    priorite: Optional[str] = Query(None, description="Filtrer par priorité"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les ordres de remplacement générés par les alertes VNC
    """
    if not check_maintenance_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    from ...models.ordre_remplacement import OrdreRemplacement, StatutOrdreRemplacement, PrioriteOrdre
    
    query = db.query(OrdreRemplacement)
    
    if statut:
        try:
            statut_enum = StatutOrdreRemplacement(statut.upper())
            query = query.filter(OrdreRemplacement.statut == statut_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Statut invalide: {statut}")
    
    if priorite:
        try:
            priorite_enum = PrioriteOrdre(priorite.upper())
            query = query.filter(OrdreRemplacement.priorite == priorite_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Priorité invalide: {priorite}")
    
    ordres = query.order_by(OrdreRemplacement.date_creation.desc()).all()
    
    return [
        {
            "id": o.id,
            "bien_id": o.bien_id,
            "designation_bien": o.designation_bien or f"Bien #{o.bien_id}",
            "motif": o.motif,
            "priorite": o.priorite.value if o.priorite else None,
            "statut": o.statut.value if o.statut else None,
            "date_creation": o.date_creation,
            "date_echeance": o.date_echeance,
            "vnc_actuelle": o.vnc_actuelle,
            "prix_acquisition": o.prix_acquisition,
            "est_en_retard": o.est_en_retard,
            "jours_retard": o.jours_retard
        }
        for o in ordres
    ]