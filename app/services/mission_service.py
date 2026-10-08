import logging
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.mission import Mission, StatutMission
from app.models.projet import Projet
from app.models.utilisateur import Utilisateur
from app.models.affectation_mission import AffectationMission
from app.models.chauffeur import Chauffeur
from app.models.vehicule import Vehicule
from app.models.trajet import Trajet
from app.models.notification import TypeNotificationEnum
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services.workflow_service import WorkflowService
from app.services.organisation_service import OrganisationService
from app.services.config_inventaire_service import ConfigInventaireService
from app.services.affectation_service import _has_overlap, AffectationConflict, create_affectation
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class MissionWorkflowError(ValueError):
    pass


class MissionPermissionError(PermissionError):
    pass


class MissionQuotaExceeded(ValueError):
    pass


def _safe_notify(func, *args, **kwargs):
    """Exécute l'envoi de notification sans bloquer la transaction en cas d'erreur de transport."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        logger.warning(f"Notification non envoyée (erreur non bloquante) : {exc}")
        return None


def list_missions(
    db: Session,
    organisation_id: int,
    skip: int = 0,
    limit: int = 100,
    statut: str | None = None,
    chauffeur_id: int | None = None,
    vehicule_id: int | None = None,
    projet_id: int | None = None,
    date_debut: datetime | None = None,
    date_fin: datetime | None = None,
    search: str | None = None,
):
    q = db.query(Mission).filter(Mission.organisation_id == organisation_id)

    if statut:
        q = q.filter(Mission.statut == statut.strip())

    if projet_id is not None:
        q = q.filter(Mission.projet_id == projet_id)

    if chauffeur_id is not None:
        q = q.filter(
            Mission.affectations.any(
                (AffectationMission.chauffeur_id == chauffeur_id)
                & (~AffectationMission.statut.in_(["ANNULEE", "REJETEE"]))
            )
        )

    if vehicule_id is not None:
        q = q.filter(
            Mission.affectations.any(
                (AffectationMission.vehicule_id == vehicule_id)
                & (~AffectationMission.statut.in_(["ANNULEE", "REJETEE"]))
            )
        )

    if date_debut is not None:
        q = q.filter(Mission.date_debut >= date_debut)

    if date_fin is not None:
        q = q.filter(Mission.date_fin <= date_fin)

    if search:
        search_filter = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Mission.numero_mission.ilike(search_filter),
                Mission.description.ilike(search_filter),
                Mission.lieu_depart.ilike(search_filter),
                Mission.lieu_arrivee.ilike(search_filter),
            )
        )

    return q.order_by(Mission.date_creation.desc()).offset(skip).limit(limit).all()


def get_mission(db: Session, mission_id: int, organisation_id: int) -> Mission | None:
    return (
        db.query(Mission)
        .filter(Mission.id == mission_id, Mission.organisation_id == organisation_id)
        .first()
    )


def _verify_project(db: Session, projet_id: int | None, organisation_id: int) -> None:
    if projet_id is None:
        return
    projet = db.query(Projet.id).filter(
        Projet.id == projet_id,
        Projet.organisation_id == organisation_id,
    ).first()
    if not projet:
        raise ValueError("Le projet est introuvable dans cette organisation")


def create_mission(
    db: Session,
    data: MissionCreate,
    organisation_id: int,
    user_id: int | None = None,
) -> Mission:
    # Vérification quota missions du mois si configuré
    quota = OrganisationService(db).verifier_quota(organisation_id, "missions")
    if not quota.get("est_disponible", True):
        raise MissionQuotaExceeded(quota.get("message", "Quota de missions dépassé pour ce mois"))

    try:
        values = data.model_dump()
        values.pop("statut", None)
        _verify_project(db, values.get("projet_id"), organisation_id)
        numero_mission = ConfigInventaireService(db).generer_numero_mission(organisation_id)
        obj = Mission(
            **values,
            numero_mission=numero_mission,
            organisation_id=organisation_id,
            cree_par=user_id,
            statut=StatutMission.BROUILLON.value,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)

        # Audit
        try:
            AuditService(db).log_action(
                user_id=user_id,
                table_name="missions",
                record_id=obj.id,
                action="CREATION_MISSION",
                nouvelles_valeurs={
                    "numero_mission": obj.numero_mission,
                    "statut": obj.statut,
                    "projet_id": obj.projet_id,
                    "destination": obj.destination,
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Erreur d'audit à la création de mission: {e}")

        return obj
    except Exception:
        db.rollback()
        raise


def update_mission(
    db: Session,
    mission_id: int,
    data: MissionUpdate,
    organisation_id: int,
    user_id: int | None = None,
) -> Mission | None:
    try:
        obj = get_mission(db, mission_id, organisation_id)
        if not obj:
            return None
        if obj.statut not in (StatutMission.BROUILLON.value, StatutMission.REJETEE.value, "DEMANDE"):
            raise MissionWorkflowError("Seule une mission en brouillon ou rejetée peut être modifiée")

        changes = data.model_dump(exclude_unset=True)
        if "projet_id" in changes:
            _verify_project(db, changes["projet_id"], organisation_id)

        anciennes_valeurs = {k: getattr(obj, k) for k in changes if hasattr(obj, k)}
        for key, value in changes.items():
            setattr(obj, key, value)

        db.commit()
        db.refresh(obj)

        try:
            AuditService(db).log_action(
                user_id=user_id,
                table_name="missions",
                record_id=obj.id,
                action="MODIFICATION_MISSION",
                anciennes_valeurs=anciennes_valeurs,
                nouvelles_valeurs=changes,
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Erreur audit modification mission: {e}")

        return obj
    except Exception:
        db.rollback()
        raise


def delete_mission(
    db: Session,
    mission_id: int,
    organisation_id: int,
    user_id: int | None = None,
) -> bool:
    obj = get_mission(db, mission_id, organisation_id)
    if not obj:
        return False
    if obj.statut in (
        StatutMission.VALIDEE.value,
        StatutMission.VALIDEE_LOG.value,
        StatutMission.VALIDEE_DG.value,
        StatutMission.PLANIFIEE.value,
        StatutMission.EN_COURS.value,
        StatutMission.TERMINEE.value,
    ):
        raise MissionWorkflowError(f"Impossible de supprimer une mission au statut '{obj.statut}'")

    try:
        AuditService(db).log_action(
            user_id=user_id,
            table_name="missions",
            record_id=obj.id,
            action="SUPPRESSION_MISSION",
            anciennes_valeurs={"numero_mission": obj.numero_mission, "statut": obj.statut},
        )
    except Exception as e:
        logger.warning(f"Erreur audit suppression mission: {e}")

    db.delete(obj)
    db.commit()
    return True


def soumettre_mission(db: Session, mission_id: int, organisation_id: int, user: Utilisateur):
    mission = get_mission(db, mission_id, organisation_id)
    if not mission:
        raise ValueError("Mission introuvable")
    if mission.statut not in (StatutMission.BROUILLON.value, StatutMission.REJETEE.value, "DEMANDE"):
        raise MissionWorkflowError(
            f"Impossible de soumettre une mission au statut '{mission.statut}' (attendu: BROUILLON, DEMANDE ou REJETEE)"
        )

    wf_service = WorkflowService(db)
    premiere_etape = wf_service.obtenir_premiere_etape("MISSION", organisation_id)

    mission.statut = StatutMission.EN_ATTENTE_VALIDATION.value
    if premiere_etape:
        mission.etape_actuelle_id = premiere_etape.id
    else:
        mission.etape_actuelle_id = None

    mission.motif_rejet = None
    db.commit()
    db.refresh(mission)

    # Audit & Notification
    try:
        AuditService(db).log_action(
            user_id=user.id if user else None,
            table_name="missions",
            record_id=mission.id,
            action="SOUMISSION_MISSION",
            nouvelles_valeurs={"statut": mission.statut, "etape_actuelle_id": mission.etape_actuelle_id},
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit soumission: {e}")

    _safe_notify(
        NotificationService(db).envoyer_notification_par_role_avec_ong,
        role_nom="LOGISTICIEN",
        organisation_id=organisation_id,
        type_notif=TypeNotificationEnum.MISSION_A_VALIDER,
        titre=f"Mission à valider : {mission.numero_mission or f'#{mission.id}'}",
        contenu=f"Une demande de mission pour '{mission.destination or mission.lieu_arrivee}' a été soumise.",
        lien=f"/missions/{mission.id}",
    )

    return mission


def valider_mission(db: Session, mission_id: int, organisation_id: int, user: Utilisateur):
    mission = get_mission(db, mission_id, organisation_id)
    if not mission:
        raise ValueError("Mission introuvable")
    if mission.statut != StatutMission.EN_ATTENTE_VALIDATION.value:
        raise MissionWorkflowError(
            f"Seule une mission 'EN_ATTENTE_VALIDATION' peut être validée (actuel: {mission.statut})"
        )

    wf_service = WorkflowService(db)
    if mission.etape_actuelle_id:
        etape = wf_service.obtenir_etape(mission.etape_actuelle_id)
        if not etape:
            raise MissionWorkflowError("Étape de workflow introuvable")
        if not wf_service.verifier_role_autorise(etape, user):
            raise MissionPermissionError(
                f"Action non autorisée pour cette étape (rôle requis: {etape.role_requis}, permission requise: {etape.permission_requise})"
            )

        suivante = wf_service.prochaine_etape("MISSION", etape.ordre, organisation_id)
        if suivante:
            mission.etape_actuelle_id = suivante.id
            if etape.role_requis == "LOGISTICIEN":
                mission.statut = StatutMission.VALIDEE_LOG.value
        else:
            mission.statut = StatutMission.VALIDEE.value
            mission.etape_actuelle_id = None
            mission.valide_par = user.id
            mission.date_validation = datetime.utcnow()
            _recheck_affectations_conflits(db, mission)
    else:
        # Fallback sans circuit d'étapes configuré : validation par agent logistique ou DG
        perm_service = wf_service.permission_service
        has_direct_val = (
            perm_service.hasPermission(user, "MISSION_VALIDATE_LOG")
            or perm_service.hasPermission(user, "MISSION_VALIDATE_DG")
            or perm_service.hasPermission(user, "MISSION_VALIDER")
            or (getattr(user, "role", None) and getattr(user.role, "nom", "") in ("ADMIN", "LOGISTICIEN", "DG"))
        )
        if not has_direct_val:
            raise MissionPermissionError("Permission requise pour la validation de mission (MISSION_VALIDATE_LOG / MISSION_VALIDATE_DG)")
        mission.statut = StatutMission.VALIDEE.value
        mission.valide_par = user.id
        mission.date_validation = datetime.utcnow()
        _recheck_affectations_conflits(db, mission)

    db.commit()
    db.refresh(mission)

    # Audit & Notification
    try:
        AuditService(db).log_action(
            user_id=user.id if user else None,
            table_name="missions",
            record_id=mission.id,
            action="VALIDATION_MISSION",
            nouvelles_valeurs={"statut": mission.statut, "valide_par": mission.valide_par},
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit validation mission: {e}")

    if mission.cree_par:
        _safe_notify(
            NotificationService(db).envoyer_notification,
            ids_destinataires=[mission.cree_par],
            type_notif=TypeNotificationEnum.MISSION_VALIDEE,
            titre=f"Mission validée : {mission.numero_mission or f'#{mission.id}'}",
            contenu=f"Votre mission pour '{mission.destination or mission.lieu_arrivee}' a été validée avec succès.",
            lien=f"/missions/{mission.id}",
        )

    return mission


def rejeter_mission(db: Session, mission_id: int, organisation_id: int, motif: str, user: Utilisateur):
    mission = get_mission(db, mission_id, organisation_id)
    if not mission:
        raise ValueError("Mission introuvable")
    if mission.statut != StatutMission.EN_ATTENTE_VALIDATION.value:
        raise MissionWorkflowError(
            f"Seule une mission 'EN_ATTENTE_VALIDATION' peut être rejetée (actuel: {mission.statut})"
        )

    if not motif or not str(motif).strip():
        raise ValueError("Le motif du rejet est obligatoire")

    wf_service = WorkflowService(db)
    if mission.etape_actuelle_id:
        etape = wf_service.obtenir_etape(mission.etape_actuelle_id)
        if etape and not wf_service.verifier_role_autorise(etape, user):
            raise MissionPermissionError("Action non autorisée pour rejeter cette étape")

    mission.statut = StatutMission.REJETEE.value
    mission.motif_rejet = motif.strip()
    mission.etape_actuelle_id = None
    db.commit()
    db.refresh(mission)

    # Audit & Notification
    try:
        AuditService(db).log_action(
            user_id=user.id if user else None,
            table_name="missions",
            record_id=mission.id,
            action="REJET_MISSION",
            nouvelles_valeurs={"statut": mission.statut, "motif": mission.motif_rejet},
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit rejet mission: {e}")

    if mission.cree_par:
        _safe_notify(
            NotificationService(db).envoyer_notification,
            ids_destinataires=[mission.cree_par],
            type_notif=TypeNotificationEnum.MISSION_REJETEE,
            titre=f"Mission rejetée : {mission.numero_mission or f'#{mission.id}'}",
            contenu=f"Votre mission a été rejetée. Motif : {mission.motif_rejet}",
            lien=f"/missions/{mission.id}",
        )

    return mission


def affecter_mission(
    db: Session,
    mission_id: int,
    vehicule_id: int,
    chauffeur_id: int,
    date_debut: datetime,
    date_fin: datetime,
    organisation_id: int,
    commentaire: str | None = None,
    user_id: int | None = None,
):
    aff = create_affectation(
        db=db,
        data={
            "mission_id": mission_id,
            "vehicule_id": vehicule_id,
            "chauffeur_id": chauffeur_id,
            "date_debut": date_debut,
            "date_fin": date_fin,
            "commentaire": commentaire,
        },
        organisation_id=organisation_id,
    )

    try:
        AuditService(db).log_action(
            user_id=user_id,
            table_name="affectations_mission",
            record_id=aff.id,
            action="AFFECTATION_MISSION",
            nouvelles_valeurs={
                "mission_id": mission_id,
                "vehicule_id": vehicule_id,
                "chauffeur_id": chauffeur_id,
                "date_debut": str(date_debut),
                "date_fin": str(date_fin),
            },
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit affectation: {e}")

    return aff


def demarrer_mission(
    db: Session,
    mission_id: int,
    km_depart: float,
    heure_depart: datetime,
    organisation_id: int,
    user_id: int | None = None,
    photo_depart_url: str | None = None,
) -> Mission:
    mission = get_mission(db, mission_id, organisation_id)
    if not mission:
        raise ValueError("Mission introuvable")

    statuts_demarrables = (
        StatutMission.VALIDEE.value,
        StatutMission.VALIDEE_LOG.value,
        StatutMission.VALIDEE_DG.value,
        StatutMission.PLANIFIEE.value,
    )
    if mission.statut not in statuts_demarrables:
        raise MissionWorkflowError(
            f"Impossible de démarrer la mission depuis le statut '{mission.statut}' (autorisés: VALIDEE, PLANIFIEE)"
        )

    # Récupérer l'affectation active
    affectations_actives = [
        aff for aff in mission.affectations if aff.statut not in ("ANNULEE", "REJETEE")
    ]
    if not affectations_actives:
        raise MissionWorkflowError("Impossible de démarrer une mission sans véhicule et chauffeur affectés")

    aff = affectations_actives[0]

    mission.statut = StatutMission.EN_COURS.value
    mission.km_depart = float(km_depart)
    mission.heure_depart_reelle = heure_depart
    if photo_depart_url:
        mission.photo_depart_url = photo_depart_url

    # Mettre à jour le chauffeur
    if aff.chauffeur_id:
        chauffeur = (
            db.query(Chauffeur)
            .filter(Chauffeur.id == aff.chauffeur_id, Chauffeur.organisation_id == organisation_id)
            .first()
        )
        if chauffeur:
            chauffeur.statut = "EN_MISSION"
            chauffeur.disponible = False

    # Créer le trajet opérationnel
    trajet = Trajet(
        organisation_id=organisation_id,
        mission_id=mission.id,
        vehicule_id=aff.vehicule_id,
        chauffeur_id=aff.chauffeur_id,
        date_debut=heure_depart,
        kilometrage_debut=float(km_depart),
        source_donnees="MOBILE",
        statut="EN_COURS",
    )
    db.add(trajet)
    aff.statut = "EN_COURS"

    db.commit()
    db.refresh(mission)

    # Audit & Notification
    try:
        AuditService(db).log_action(
            user_id=user_id,
            table_name="missions",
            record_id=mission.id,
            action="DEMARRAGE_MISSION",
            nouvelles_valeurs={
                "statut": mission.statut,
                "km_depart": km_depart,
                "heure_depart_reelle": str(heure_depart),
            },
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit démarrage: {e}")

    if mission.cree_par:
        _safe_notify(
            NotificationService(db).envoyer_notification,
            ids_destinataires=[mission.cree_par],
            type_notif=TypeNotificationEnum.MISSION_DEMARREE,
            titre=f"Mission en cours : {mission.numero_mission or f'#{mission.id}'}",
            contenu=f"La mission pour '{mission.destination or mission.lieu_arrivee}' est officiellement démarrée.",
            lien=f"/missions/{mission.id}",
        )

    return mission


def terminer_mission(
    db: Session,
    mission_id: int,
    km_arrivee: float,
    heure_retour: datetime,
    organisation_id: int,
    user_id: int | None = None,
    observation: str | None = None,
) -> Mission:
    mission = get_mission(db, mission_id, organisation_id)
    if not mission:
        raise ValueError("Mission introuvable")

    if mission.statut != StatutMission.EN_COURS.value:
        raise MissionWorkflowError(
            f"Impossible de terminer une mission au statut '{mission.statut}' (attendu: EN_COURS)"
        )

    km_arr = float(km_arrivee)
    km_dep = float(mission.km_depart or 0.0)
    if km_arr < km_dep:
        raise MissionWorkflowError(
            f"Le kilométrage d'arrivée ({km_arr}) ne peut pas être inférieur au kilométrage de départ ({km_dep})"
        )

    mission.statut = StatutMission.TERMINEE.value
    mission.km_arrivee = km_arr
    mission.heure_retour_reelle = heure_retour
    if observation:
        mission.observation = observation

    # Clôture des affectations et mise à jour chauffeur + véhicule
    for aff in mission.affectations:
        if aff.statut in ("ANNULEE", "REJETEE"):
            continue
        aff.statut = "TERMINEE"

        if aff.chauffeur_id:
            chauffeur = (
                db.query(Chauffeur)
                .filter(Chauffeur.id == aff.chauffeur_id, Chauffeur.organisation_id == organisation_id)
                .first()
            )
            if chauffeur:
                chauffeur.statut = "DISPONIBLE"
                chauffeur.disponible = True

        if aff.vehicule_id:
            vehicule = (
                db.query(Vehicule)
                .filter(Vehicule.id_bien == aff.vehicule_id, Vehicule.organisation_id == organisation_id)
                .first()
            )
            if vehicule:
                vehicule.kilometrage_actuel = max(float(vehicule.kilometrage_actuel or 0.0), km_arr)

    # Clôture du / des trajets en cours
    trajets = (
        db.query(Trajet)
        .filter(
            Trajet.mission_id == mission.id,
            Trajet.organisation_id == organisation_id,
            Trajet.statut == "EN_COURS",
        )
        .all()
    )
    for t in trajets:
        t.date_fin = heure_retour
        t.kilometrage_fin = km_arr
        k_deb = float(t.kilometrage_debut or km_dep)
        t.distance_km = round(max(0.0, km_arr - k_deb), 2)
        t.statut = "TERMINE"

    db.commit()
    db.refresh(mission)

    # Audit & Notification
    try:
        AuditService(db).log_action(
            user_id=user_id,
            table_name="missions",
            record_id=mission.id,
            action="CLOTURE_MISSION",
            nouvelles_valeurs={
                "statut": mission.statut,
                "km_arrivee": km_arr,
                "heure_retour_reelle": str(heure_retour),
                "km_parcourus": round(max(0.0, km_arr - km_dep), 2),
            },
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit clôture: {e}")

    if mission.cree_par:
        _safe_notify(
            NotificationService(db).envoyer_notification,
            ids_destinataires=[mission.cree_par],
            type_notif=TypeNotificationEnum.MISSION_TERMINEE,
            titre=f"Mission clôturée : {mission.numero_mission or f'#{mission.id}'}",
            contenu=f"La mission #{mission.numero_mission or mission.id} est terminée (distance : {round(max(0.0, km_arr - km_dep), 2)} km).",
            lien=f"/missions/{mission.id}",
        )

    return mission


def annuler_mission(
    db: Session,
    mission_id: int,
    motif: str,
    organisation_id: int,
    user_id: int | None = None,
) -> Mission:
    mission = get_mission(db, mission_id, organisation_id)
    if not mission:
        raise ValueError("Mission introuvable")

    if mission.statut == StatutMission.TERMINEE.value:
        raise MissionWorkflowError("Impossible d'annuler une mission déjà terminée")

    if mission.statut == StatutMission.ANNULEE.value:
        raise MissionWorkflowError("La mission est déjà annulée")

    if not motif or not str(motif).strip():
        raise ValueError("Un motif d'annulation est obligatoire")

    ancien_statut = mission.statut
    mission.statut = StatutMission.ANNULEE.value
    mission.motif_rejet = motif.strip()

    # Libérer affectations & chauffeurs
    for aff in mission.affectations:
        if aff.statut != "ANNULEE":
            aff.statut = "ANNULEE"
            if aff.chauffeur_id:
                ch = (
                    db.query(Chauffeur)
                    .filter(Chauffeur.id == aff.chauffeur_id, Chauffeur.organisation_id == organisation_id)
                    .first()
                )
                if ch and ch.statut == "EN_MISSION":
                    ch.statut = "DISPONIBLE"
                    ch.disponible = True

    # Marquer les trajets en cours
    for t in (
        db.query(Trajet)
        .filter(
            Trajet.mission_id == mission.id,
            Trajet.organisation_id == organisation_id,
            Trajet.statut == "EN_COURS",
        )
        .all()
    ):
        t.statut = "ANOMALIE"

    db.commit()
    db.refresh(mission)

    try:
        AuditService(db).log_action(
            user_id=user_id,
            table_name="missions",
            record_id=mission.id,
            action="ANNULATION_MISSION",
            anciennes_valeurs={"statut": ancien_statut},
            nouvelles_valeurs={"statut": "ANNULEE", "motif": mission.motif_rejet},
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit annulation: {e}")

    return mission


def _recheck_affectations_conflits(db: Session, mission: Mission):
    """Re-contrôle l'absence de chevauchement lors de la validation finale."""
    for aff in mission.affectations:
        if aff.statut in ("ANNULEE", "REJETEE"):
            continue
        if aff.vehicule_id and _has_overlap(
            db,
            AffectationMission,
            AffectationMission.vehicule_id,
            aff.vehicule_id,
            mission.organisation_id,
            aff.date_debut,
            aff.date_fin,
            exclude_id=aff.id,
        ):
            raise AffectationConflict(
                f"Conflit détecté lors de la validation : le véhicule #{aff.vehicule_id} est déjà affecté sur cette période"
            )
        if aff.chauffeur_id and _has_overlap(
            db,
            AffectationMission,
            AffectationMission.chauffeur_id,
            aff.chauffeur_id,
            mission.organisation_id,
            aff.date_debut,
            aff.date_fin,
            exclude_id=aff.id,
        ):
            raise AffectationConflict(
                f"Conflit détecté lors de la validation : le chauffeur #{aff.chauffeur_id} est déjà affecté sur cette période"
            )


class MissionService:
    """Service orienté objet pour les missions de flotte OKAPI."""

    def __init__(self, db: Session):
        self.db = db

    def list(self, organisation_id: int, skip: int = 0, limit: int = 100, **filters):
        return list_missions(self.db, organisation_id, skip=skip, limit=limit, **filters)

    def get(self, mission_id: int, organisation_id: int) -> Mission | None:
        return get_mission(self.db, mission_id, organisation_id)

    def creer(self, data: MissionCreate, organisation_id: int, user_id: int | None = None) -> Mission:
        return create_mission(self.db, data, organisation_id, user_id=user_id)

    def update(self, mission_id: int, data: MissionUpdate, organisation_id: int, user_id: int | None = None) -> Mission | None:
        return update_mission(self.db, mission_id, data, organisation_id, user_id=user_id)

    def supprimer(self, mission_id: int, organisation_id: int, user_id: int | None = None) -> bool:
        return delete_mission(self.db, mission_id, organisation_id, user_id=user_id)

    def soumettre(self, mission_id: int, organisation_id: int, user: Utilisateur) -> Mission:
        return soumettre_mission(self.db, mission_id, organisation_id, user)

    def valider(self, mission_id: int, organisation_id: int, user: Utilisateur) -> Mission:
        return valider_mission(self.db, mission_id, organisation_id, user)

    def rejeter(self, mission_id: int, organisation_id: int, motif: str, user: Utilisateur) -> Mission:
        return rejeter_mission(self.db, mission_id, organisation_id, motif, user)

    def affecter(
        self,
        mission_id: int,
        vehicule_id: int,
        chauffeur_id: int,
        date_debut: datetime,
        date_fin: datetime,
        organisation_id: int,
        commentaire: str | None = None,
        user_id: int | None = None,
    ):
        return affecter_mission(
            self.db,
            mission_id=mission_id,
            vehicule_id=vehicule_id,
            chauffeur_id=chauffeur_id,
            date_debut=date_debut,
            date_fin=date_fin,
            organisation_id=organisation_id,
            commentaire=commentaire,
            user_id=user_id,
        )

    def demarrer(
        self,
        mission_id: int,
        km_depart: float,
        heure_depart: datetime,
        organisation_id: int,
        user_id: int | None = None,
        photo_depart_url: str | None = None,
    ) -> Mission:
        return demarrer_mission(
            self.db,
            mission_id=mission_id,
            km_depart=km_depart,
            heure_depart=heure_depart,
            organisation_id=organisation_id,
            user_id=user_id,
            photo_depart_url=photo_depart_url,
        )

    def terminer(
        self,
        mission_id: int,
        km_arrivee: float,
        heure_retour: datetime,
        organisation_id: int,
        user_id: int | None = None,
        observation: str | None = None,
    ) -> Mission:
        return terminer_mission(
            self.db,
            mission_id=mission_id,
            km_arrivee=km_arrivee,
            heure_retour=heure_retour,
            organisation_id=organisation_id,
            user_id=user_id,
            observation=observation,
        )

    def annuler(
        self,
        mission_id: int,
        motif: str,
        organisation_id: int,
        user_id: int | None = None,
    ) -> Mission:
        return annuler_mission(
            self.db,
            mission_id=mission_id,
            motif=motif,
            organisation_id=organisation_id,
            user_id=user_id,
        )