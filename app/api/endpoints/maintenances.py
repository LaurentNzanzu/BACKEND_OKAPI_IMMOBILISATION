# backend/app/api/endpoints/maintenances.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...schemas.maintenance import (
    MaintenanceCreate, MaintenanceUpdate, MaintenanceResponse,
    MaintenanceListResponse, MaintenanceReporter, MaintenanceTerminer,
    MaintenanceStatistics
)
from ...services.maintenance_service import MaintenanceService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur

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