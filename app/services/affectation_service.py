import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.affectation_mission import AffectationMission
from app.models.mission import Mission
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.models.bien import EtatBien, StatutComptable
from app.models.maintenance import Maintenance, StatutMaintenance
from app.models.notification import TypeNotificationEnum
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AffectationConflict(ValueError):
    pass


def _has_overlap(
    db: Session,
    model,
    resource_field,
    resource_id: int,
    organisation_id: int,
    date_debut: datetime,
    date_fin: datetime,
    exclude_id: int | None = None,
):
    q = db.query(model).filter(
        model.organisation_id == organisation_id,
        resource_field == resource_id,
        model.date_debut < date_fin,
        model.date_fin > date_debut,
        ~model.statut.in_(["ANNULEE", "REJETEE"]),
    )
    if exclude_id:
        q = q.filter(model.id != exclude_id)
    return q.first() is not None


CATEGORIE_PERMIS_COMPATIBILITE = {
    "MOTO": {"A", "A1", "A2"},
    "VOITURE": {"B", "B1", "C", "C1", "D", "E"},
    "CAMION": {"C", "C1", "CE", "E"},
    "BUS": {"D", "D1", "DE"},
}


def verifier_compatibilite_permis(categorie_vehicule: str | None, categorie_permis: str | None) -> bool:
    if not categorie_vehicule or not categorie_permis:
        return True
    cat_veh = str(categorie_vehicule).strip().upper()
    cat_perm = str(categorie_permis).strip().upper()
    permis_acceptes = CATEGORIE_PERMIS_COMPATIBILITE.get(cat_veh)
    if not permis_acceptes:
        return True
    return any(p in cat_perm for p in permis_acceptes)


def verifier_maintenance_vehicule(
    db: Session,
    vehicule_id: int,
    organisation_id: int,
    date_debut: datetime,
    date_fin: datetime,
) -> None:
    maints = db.query(Maintenance).filter(
        Maintenance.id_bien == vehicule_id,
        Maintenance.organisation_id == organisation_id,
        ~Maintenance.statut.in_([StatutMaintenance.TERMINEE, StatutMaintenance.ANNULEE]),
    ).all()
    for m in maints:
        m_debut = m.date_debut_reelle or m.date_planifiee
        m_fin = m.date_fin_reelle or (m_debut + timedelta(days=1))
        if m_debut < date_fin and m_fin > date_debut:
            raise AffectationConflict(
                f"Véhicule indisponible : maintenance #{m.id_maintenance} ({m.type_maintenance.value}) prévue du {m_debut} au {m_fin}"
            )


def create_affectation(db: Session, data: dict, organisation_id: int, user_id: int | None = None):
    try:
        mission_id = data.get("mission_id")
        vehicule_id = data.get("vehicule_id")
        chauffeur_id = data.get("chauffeur_id")
        date_debut = data["date_debut"]
        date_fin = data["date_fin"]

        if date_debut >= date_fin:
            raise ValueError("date_debut doit être antérieure à date_fin")

        mission = db.query(Mission).filter(
            Mission.id == mission_id, Mission.organisation_id == organisation_id
        ).with_for_update().first()
        if not mission:
            raise ValueError("Mission introuvable dans cette organisation")
        if mission.statut in ("ANNULEE", "REJETEE"):
            raise ValueError(f"Impossible d'affecter une ressource à une mission {mission.statut.lower()}")

        vehicule = None
        if vehicule_id is not None:
            vehicule = db.query(Vehicule).filter(
                Vehicule.id_bien == vehicule_id, Vehicule.organisation_id == organisation_id
            ).with_for_update().first()
            if not vehicule:
                raise ValueError("Véhicule introuvable dans cette organisation")

            # 1. Vérification état patrimonial
            etat_val = getattr(vehicule.etat, "value", vehicule.etat)
            if etat_val in ("PANNE", "MAINTENANCE", "REFORME") or vehicule.etat in (EtatBien.PANNE, EtatBien.MAINTENANCE, EtatBien.REFORME):
                raise AffectationConflict(f"Véhicule non disponible : état patrimonial '{etat_val}'")
            if vehicule.statut_comptable in (StatutComptable.CEDE.value, StatutComptable.MIS_AU_REBUT.value, StatutComptable.HORS_SERVICE.value):
                raise AffectationConflict(f"Véhicule non disponible : statut comptable '{vehicule.statut_comptable}'")

            # 2. Maintenances planifiées chevauchant la période
            verifier_maintenance_vehicule(db, vehicule_id, organisation_id, date_debut, date_fin)

            # 3. Chevauchement avec d'autres affectations actives
            if _has_overlap(
                db, AffectationMission, AffectationMission.vehicule_id,
                vehicule_id, organisation_id, date_debut, date_fin
            ):
                raise AffectationConflict("Véhicule déjà affecté sur cette période")

        chauffeur = None
        if chauffeur_id is not None:
            chauffeur = db.query(Chauffeur).filter(
                Chauffeur.id == chauffeur_id, Chauffeur.organisation_id == organisation_id
            ).with_for_update().first()
            if not chauffeur:
                raise ValueError("Chauffeur introuvable dans cette organisation")
            if not chauffeur.actif:
                raise AffectationConflict("Le chauffeur sélectionné est inactif")
            if chauffeur.date_expiration_permis and chauffeur.date_expiration_permis < date_fin.date():
                raise AffectationConflict(f"Le permis du chauffeur est expiré (date d'expiration : {chauffeur.date_expiration_permis.isoformat()})")

            if _has_overlap(
                db, AffectationMission, AffectationMission.chauffeur_id,
                chauffeur_id, organisation_id, date_debut, date_fin
            ):
                raise AffectationConflict("Chauffeur déjà affecté sur cette période")

        # Vérification compatibilité permis chauffeur <-> catégorie véhicule
        if vehicule and chauffeur:
            if not verifier_compatibilite_permis(vehicule.categorie, chauffeur.categorie_permis):
                raise AffectationConflict(
                    f"Catégorie de permis incompatible : le chauffeur possède le permis '{chauffeur.categorie_permis}' incompatible avec un véhicule de catégorie '{vehicule.categorie}'"
                )

        allowed_fields = {
            "mission_id", "vehicule_id", "chauffeur_id", "date_debut", "date_fin",
            "statut", "commentaire",
        }
        obj = AffectationMission(
            **{key: value for key, value in data.items() if key in allowed_fields},
            organisation_id=organisation_id,
            affecte_par=user_id,
            date_affectation=datetime.utcnow(),
        )
        db.add(obj)

        # Si la mission était validée, passer à PLANIFIEE
        if mission.statut == "VALIDEE":
            mission.statut = "PLANIFIEE"

        db.commit()
        db.refresh(obj)

        # Audit de traçabilité
        try:
            AuditService(db).log_action(
                user_id=user_id,
                table_name="affectations_mission",
                record_id=obj.id,
                action="AFFECTATION_RESSOURCES",
                nouvelles_valeurs={
                    "mission_id": obj.mission_id,
                    "vehicule_id": obj.vehicule_id,
                    "chauffeur_id": obj.chauffeur_id,
                    "date_debut": obj.date_debut.isoformat() if obj.date_debut else None,
                    "date_fin": obj.date_fin.isoformat() if obj.date_fin else None,
                    "statut": obj.statut,
                    "affecte_par": user_id,
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Erreur audit affectation: {e}")

        # Notification au demandeur et au chauffeur
        destinataires = []
        if mission.cree_par:
            destinataires.append(mission.cree_par)
        if chauffeur and chauffeur.utilisateur_id:
            destinataires.append(chauffeur.utilisateur_id)

        if destinataires:
            try:
                NotificationService(db).envoyer_notification(
                    ids_destinataires=destinataires,
                    type_notif=TypeNotificationEnum.MISSION_VALIDEE,
                    titre=f"Ressource affectée à la mission : {mission.numero_mission or f'#{mission.id}'}",
                    contenu=f"Véhicule/chauffeur affecté(s) pour la mission vers '{mission.lieu_arrivee}'.",
                    lien=f"/missions/{mission.id}",
                )
            except Exception as e:
                logger.warning(f"Erreur notification affectation: {e}")

        return obj
    except Exception:
        db.rollback()
        raise


def list_affectations(db: Session, organisation_id: int):
    return (
        db.query(AffectationMission)
        .filter(AffectationMission.organisation_id == organisation_id)
        .all()
    )


def get_affectation(db: Session, affectation_id: int, organisation_id: int):
    return (
        db.query(AffectationMission)
        .filter(
            AffectationMission.id == affectation_id,
            AffectationMission.organisation_id == organisation_id,
        )
        .first()
    )


def delete_affectation(db: Session, affectation_id: int, organisation_id: int, user_id: int | None = None):
    obj = get_affectation(db, affectation_id, organisation_id)
    if not obj:
        return False
    aff_id = obj.id
    db.delete(obj)
    db.commit()
    try:
        AuditService(db).log_action(
            user_id=user_id,
            table_name="affectations_mission",
            record_id=aff_id,
            action="SUPPRESSION_AFFECTATION",
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Erreur audit suppression affectation: {e}")
    return True