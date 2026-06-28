# backend/app/api/endpoints/notifications.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ...core.database import get_db
from ...schemas.notification import NotificationResponse, PrioriteNotificationEnum
from ...services.notification_service import NotificationService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", response_model=List[NotificationResponse])
def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    est_lu: Optional[bool] = Query(None, description="True=lues, False=non lues"),
    priorite: Optional[PrioriteNotificationEnum] = Query(
        None, description="information | importante | critique"
    ),
    include_archivees: bool = Query(False, description="Inclure les notifications archivées"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Liste les notifications avec filtres optionnels.

    - **est_lu** : filtre lu / non lu (par utilisateur)
    - **priorite** : information | importante | critique
    - **include_archivees** : afficher aussi les notifications archivées
    """
    service = NotificationService(db)
    role = current_user.role.nom.upper() if current_user.role else "USER"
    priorite_value = priorite.value if priorite else None

    if role in ["ADMIN", "DG"]:
        notifications = service.get_all_notifications_for_admin(
            current_user.id,
            limit,
            skip=skip,
            est_lu=est_lu,
            priorite=priorite_value,
            include_archivees=include_archivees,
        )
    else:
        notifications = service.get_notifications_by_user(
            current_user.id,
            limit,
            skip=skip,
            est_lu=est_lu,
            priorite=priorite_value,
            include_archivees=include_archivees,
        )

    return notifications


@router.get("/non-lues/count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Compte les notifications non lues et non archivées de l'utilisateur."""
    return {"count": NotificationService(db).get_non_lues_count(current_user.id)}


@router.patch("/{id_notification}/lu")
def mark_as_read(
    id_notification: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    service = NotificationService(db)
    success = service.marquer_comme_lue(id_notification, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification introuvable")

    return {"success": True, "message": "Notification marquée comme lue"}


@router.patch("/{id_notification}/archiver")
def archive_notification(
    id_notification: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Archive une notification pour l'utilisateur courant (sans suppression)."""
    service = NotificationService(db)
    success = service.archiver_notification(id_notification, current_user.id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Notification introuvable ou non autorisée",
        )

    return {"success": True, "message": "Notification archivée"}


@router.post("/tout-marquer-lu")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    count = NotificationService(db).marquer_tout_comme_lu(current_user.id)
    return {"message": f"{count} notification(s) marquée(s) comme lue(s)"}
