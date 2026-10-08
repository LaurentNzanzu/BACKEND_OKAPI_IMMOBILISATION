"""Véhicule = extension opérationnelle d'un Bien patrimonial (option A)."""
from sqlalchemy.orm import Session

from app.models.localisation import Localisation
from app.models.organisation import Organisation
from app.models.type_bien import TypeBien
from app.models.vehicule import Vehicule
from app.schemas.vehicule import VehiculeCreate, VehiculeUpdate
from app.services.organisation_service import OrganisationService


VEHICULE_FIELDS = {
    "type_vehicule", "marque", "modele", "immatriculation", "poids", "dimension",
    "type_carburant", "consommation_carburant", "consommation_huile", "type_propulsion",
}


from app.models.amortissement import Amortissement
from app.models.ecriture_comptable import EcritureComptable
from app.models.affectation_mission import AffectationMission
from app.models.trajet import Trajet
from app.models.mouvement_bien import MouvementBien
from app.models.maintenance import Maintenance


class VehiculeQuotaExceeded(ValueError):
    pass


class ImmatriculationConflict(ValueError):
    pass


class VehiculeHasHistoryConflict(ValueError):
    pass


def list_vehicules(
    db: Session,
    organisation_id: int,
    skip: int = 0,
    limit: int = 100,
    type_vehicule: str | None = None,
):
    query = (
        db.query(Vehicule)
        .filter(Vehicule.organisation_id == organisation_id)
    )
    if type_vehicule:
        query = query.filter(Vehicule.type_vehicule == type_vehicule)
    return query.offset(skip).limit(limit).all()


def get_vehicule(db: Session, id_bien: int, organisation_id: int):
    return (
        db.query(Vehicule)
        .filter(Vehicule.id_bien == id_bien, Vehicule.organisation_id == organisation_id)
        .first()
    )


def get_vehicule_by_immat(db: Session, immatriculation: str, organisation_id: int):
    return (
        db.query(Vehicule)
        .filter(
            Vehicule.immatriculation == immatriculation,
            Vehicule.organisation_id == organisation_id,
        )
        .first()
    )


def _verify_localisation(db: Session, id_localisation: int, organisation_id: int) -> None:
    exists = db.query(Localisation.id_localisation).filter(
        Localisation.id_localisation == id_localisation,
        Localisation.organisation_id == organisation_id,
    ).first()
    if not exists:
        raise ValueError("Localisation introuvable dans cette organisation")


def _verify_quota(db: Session, organisation_id: int) -> None:
    result = OrganisationService(db).verifier_quota(organisation_id, "vehicules")
    if not result["est_disponible"]:
        raise VehiculeQuotaExceeded(result["message"])


def create_vehicule(db: Session, data: VehiculeCreate, organisation_id: int):
    try:
        organisation = (
            db.query(Organisation)
            .filter(Organisation.id == organisation_id)
            .with_for_update()
            .one_or_none()
        )
        if not organisation:
            raise ValueError("Organisation introuvable")
        _verify_quota(db, organisation_id)
        _verify_localisation(db, data.id_localisation, organisation_id)

        type_bien = db.query(TypeBien).filter(TypeBien.code == "VEHICULE").first()
        if not type_bien:
            raise ValueError("Le TypeBien de code VEHICULE n'est pas configuré")
        if get_vehicule_by_immat(db, data.immatriculation, organisation_id):
            raise ImmatriculationConflict("Immatriculation déjà utilisée pour cette organisation")

        # SQLAlchemy inserts the Bien parent before the Vehicule extension on flush.
        parent_fields = {
            "organisation_id": organisation_id,
            "id_localisation": data.id_localisation,
            "numero_inventaire": data.numero_inventaire,
            "id_type_bien": type_bien.id,
            "description": data.description or data.libelle,
            "date_acquisition": data.date_acquisition,
            "prix_acquisition": data.prix_acquisition,
            "date_fin_garantie": data.date_fin_garantie,
        }
        operational_fields = data.model_dump(include=VEHICULE_FIELDS)
        vehicle = Vehicule(**parent_fields, **operational_fields)
        db.add(vehicle)
        db.flush()
        db.commit()
        db.refresh(vehicle)
        return vehicle
    except Exception:
        db.rollback()
        raise


def update_vehicule(db: Session, id_bien: int, data: VehiculeUpdate, organisation_id: int):
    try:
        db.query(Organisation).filter(Organisation.id == organisation_id).with_for_update().one_or_none()
        vehicle = get_vehicule(db, id_bien, organisation_id)
        if not vehicle:
            return None

        changes = data.model_dump(exclude_unset=True)
        if "immatriculation" in changes and changes["immatriculation"] != vehicle.immatriculation:
            if get_vehicule_by_immat(db, changes["immatriculation"], organisation_id):
                raise ImmatriculationConflict("Immatriculation déjà utilisée pour cette organisation")
        if changes.get("id_localisation") is not None:
            _verify_localisation(db, changes["id_localisation"], organisation_id)
        for key, value in changes.items():
            setattr(vehicle, key, value)
        db.commit()
        db.refresh(vehicle)
        return vehicle
    except Exception:
        db.rollback()
        raise


def delete_vehicule(db: Session, id_bien: int, organisation_id: int):
    try:
        vehicle = get_vehicule(db, id_bien, organisation_id)
        if not vehicle:
            return False

        has_history = (
            db.query(Amortissement.id_amortissement).filter(Amortissement.id_bien == id_bien).first() is not None
            or db.query(EcritureComptable.id_ecriture).filter(EcritureComptable.id_bien == id_bien).first() is not None
            or db.query(AffectationMission.id).filter(AffectationMission.vehicule_id == id_bien).first() is not None
            or db.query(Trajet.id).filter(Trajet.vehicule_id == id_bien).first() is not None
            or db.query(MouvementBien.id_mouvement).filter(MouvementBien.id_bien == id_bien).first() is not None
            or db.query(Maintenance.id_maintenance).filter(Maintenance.id_bien == id_bien).first() is not None
        )
        if has_history:
            raise VehiculeHasHistoryConflict(
                "Suppression refusée : ce véhicule possède un historique comptable, opérationnel ou patrimonial. "
                "Veuillez procéder à une mise au rebut ou une cession (REFORME)."
            )

        db.delete(vehicle)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def verifier_expirations_vehicules(db: Session, jours_preavis: int = 15, organisation_id: int | None = None) -> list:
    """Contrôle automatique de l'expiration imminente des assurances et contrôles techniques."""
    from datetime import date, timedelta
    from app.models.notification import TypeNotificationEnum
    from app.services.notification_service import NotificationService

    limite = date.today() + timedelta(days=jours_preavis)
    query = db.query(Vehicule)
    if organisation_id is not None:
        query = query.filter(Vehicule.organisation_id == organisation_id)

    vehicules = query.all()
    notif_service = NotificationService(db)
    notifs_creees = []

    for v in vehicules:
        # Assurance
        if v.date_expiration_assurance and v.date_expiration_assurance <= limite:
            jours_restants = (v.date_expiration_assurance - date.today()).days
            titre = f"Assurance expire bientôt : {v.immatriculation or v.designation}"
            contenu = (
                f"L'assurance du véhicule {v.immatriculation} expire le {v.date_expiration_assurance.isoformat()} "
                f"({jours_restants} jour(s) restant(s))."
            )
            n = notif_service.envoyer_notification_par_role_avec_ong(
                role_nom="LOGISTICIEN",
                organisation_id=v.organisation_id,
                type_notif=TypeNotificationEnum.ASSURANCE_EXPIRE_BIENTOT,
                titre=titre,
                contenu=contenu,
                lien=f"/vehicules/{v.id_bien}",
            )
            if n:
                notifs_creees.append(n)

        # Contrôle technique / Visite technique
        if v.date_expiration_visite_technique and v.date_expiration_visite_technique <= limite:
            jours_restants = (v.date_expiration_visite_technique - date.today()).days
            titre = f"Visite technique expire bientôt : {v.immatriculation or v.designation}"
            contenu = (
                f"Le contrôle technique du véhicule {v.immatriculation} expire le {v.date_expiration_visite_technique.isoformat()} "
                f"({jours_restants} jour(s) restant(s))."
            )
            n = notif_service.envoyer_notification_par_role_avec_ong(
                role_nom="LOGISTICIEN",
                organisation_id=v.organisation_id,
                type_notif=TypeNotificationEnum.VISITE_TECHNIQUE_BIENTOT,
                titre=titre,
                contenu=contenu,
                lien=f"/vehicules/{v.id_bien}",
            )
            if n:
                notifs_creees.append(n)

    return notifs_creees