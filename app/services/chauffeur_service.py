from sqlalchemy.orm import Session
from app.models.chauffeur import Chauffeur
from app.models.affectation_mission import AffectationMission
from app.models.trajet import Trajet
from app.models.utilisateur import Utilisateur
from app.schemas.chauffeur import ChauffeurCreate, ChauffeurUpdate
from app.services.organisation_service import OrganisationService


class ChauffeurQuotaExceeded(ValueError):
    pass


class ChauffeurUserConflict(ValueError):
    pass


class ChauffeurPermisConflict(ValueError):
    pass


from sqlalchemy import or_

def list_chauffeurs(
    db: Session,
    organisation_id: int,
    skip: int = 0,
    limit: int = 100,
    statut: str | None = None,
    search: str | None = None,
):
    q = db.query(Chauffeur).filter(Chauffeur.organisation_id == organisation_id)
    if statut:
        q = q.filter(Chauffeur.statut == statut.strip())
    if search:
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Chauffeur.nom.ilike(s),
                Chauffeur.prenom.ilike(s),
                Chauffeur.telephone.ilike(s),
                Chauffeur.numero_permis.ilike(s),
            )
        )
    return q.offset(skip).limit(limit).all()


def get_chauffeur(db: Session, chauffeur_id: int, organisation_id: int):
    return (
        db.query(Chauffeur)
        .filter(Chauffeur.id == chauffeur_id, Chauffeur.organisation_id == organisation_id)
        .first()
    )


def _verify_user_and_permis(db: Session, organisation_id: int, utilisateur_id: int | None, numero_permis: str | None, exclude_id: int | None = None):
    if utilisateur_id is not None:
        user = db.query(Utilisateur).filter(
            Utilisateur.id == utilisateur_id,
            (Utilisateur.organisation_id == organisation_id) | (Utilisateur.organisation_id.is_(None))
        ).first()
        if not user:
            raise ValueError("Utilisateur introuvable dans cette organisation")

        q_user = db.query(Chauffeur.id).filter(
            Chauffeur.organisation_id == organisation_id,
            Chauffeur.utilisateur_id == utilisateur_id,
            Chauffeur.actif == True,
        )
        if exclude_id:
            q_user = q_user.filter(Chauffeur.id != exclude_id)
        if q_user.first():
            raise ChauffeurUserConflict("Cet utilisateur est déjà associé à un profil chauffeur actif dans cette organisation")

    if numero_permis is not None:
        q_permis = db.query(Chauffeur.id).filter(
            Chauffeur.organisation_id == organisation_id,
            Chauffeur.numero_permis == numero_permis,
        )
        if exclude_id:
            q_permis = q_permis.filter(Chauffeur.id != exclude_id)
        if q_permis.first():
            raise ChauffeurPermisConflict("Ce numéro de permis est déjà enregistré dans cette organisation")


def create_chauffeur(db: Session, data: ChauffeurCreate, organisation_id: int):
    quota = OrganisationService(db).verifier_quota(organisation_id, "chauffeurs")
    if not quota["est_disponible"]:
        raise ChauffeurQuotaExceeded(quota["message"])
    _verify_user_and_permis(db, organisation_id, data.utilisateur_id, data.numero_permis)
    try:
        obj = Chauffeur(**data.model_dump(), organisation_id=organisation_id)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def update_chauffeur(db: Session, chauffeur_id: int, data: ChauffeurUpdate, organisation_id: int):
    obj = get_chauffeur(db, chauffeur_id, organisation_id)
    if not obj:
        return None
    changes = data.model_dump(exclude_unset=True)
    if "utilisateur_id" in changes or "numero_permis" in changes:
        new_user = changes.get("utilisateur_id", obj.utilisateur_id)
        new_permis = changes.get("numero_permis", obj.numero_permis)
        _verify_user_and_permis(db, organisation_id, new_user, new_permis, exclude_id=chauffeur_id)
    for key, value in changes.items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete_chauffeur(db: Session, chauffeur_id: int, organisation_id: int):
    obj = get_chauffeur(db, chauffeur_id, organisation_id)
    if not obj:
        return False
    # Vérification de l'historique d'affectations ou de trajets
    has_history = (
        db.query(AffectationMission.id).filter(AffectationMission.chauffeur_id == chauffeur_id).first() is not None
        or db.query(Trajet.id).filter(Trajet.chauffeur_id == chauffeur_id).first() is not None
    )
    if has_history:
        # Conservation de l'historique via désactivation logique
        obj.actif = False
        obj.disponible = False
        db.commit()
        return True
    else:
        # Suppression physique autorisée si aucune mission n'y est rattachée (création par erreur)
        db.delete(obj)
        db.commit()
        return True


def get_chauffeurs_disponibles(
    db: Session,
    organisation_id: int,
    date_debut,
    date_fin,
    zone: str | None = None,
    categorie_permis: str | None = None,
):
    from datetime import datetime
    from app.services.affectation_service import _has_overlap

    if isinstance(date_debut, str):
        date_debut = datetime.fromisoformat(date_debut)
    if isinstance(date_fin, str):
        date_fin = datetime.fromisoformat(date_fin)

    chauffeurs = (
        db.query(Chauffeur)
        .filter(
            Chauffeur.organisation_id == organisation_id,
            Chauffeur.actif == True,
            Chauffeur.statut == "DISPONIBLE",
        )
        .all()
    )

    disponibles = []
    for ch in chauffeurs:
        if ch.date_expiration_permis and ch.date_expiration_permis < date_fin.date():
            continue
        if categorie_permis and ch.categorie_permis:
            if categorie_permis.strip().upper() not in ch.categorie_permis.strip().upper():
                continue
        if _has_overlap(
            db, AffectationMission, AffectationMission.chauffeur_id,
            ch.id, organisation_id, date_debut, date_fin
        ):
            continue
        disponibles.append(ch)

    return disponibles


def verifier_expirations(db: Session, organisation_id: int | None = None) -> list[dict]:
    """
    Détecte les expirations sous 30 jours :
    - Permis de conduire des chauffeurs
    - Assurance, visite technique, permis transport des véhicules
    Retourne la liste des alertes détectées.
    """
    from datetime import date, timedelta
    from app.models.vehicule import Vehicule

    aujourdhui = date.today()
    seuil = aujourdhui + timedelta(days=30)
    alertes = []

    # 1. Chauffeurs
    q_ch = db.query(Chauffeur).filter(
        Chauffeur.actif == True,
        Chauffeur.date_expiration_permis.isnot(None),
        Chauffeur.date_expiration_permis <= seuil,
        Chauffeur.date_expiration_permis >= aujourdhui,
    )
    if organisation_id:
        q_ch = q_ch.filter(Chauffeur.organisation_id == organisation_id)

    for ch in q_ch.all():
        alertes.append({
            "type": "PERMIS_EXPIRE_BIENTOT",
            "cible_type": "chauffeur",
            "cible_id": ch.id,
            "organisation_id": ch.organisation_id,
            "titre": f"Permis de conduire bientôt expiré : {ch.prenom} {ch.nom}",
            "date_expiration": ch.date_expiration_permis.isoformat(),
            "jours_restants": (ch.date_expiration_permis - aujourdhui).days,
        })

    # 2. Véhicules
    q_veh = db.query(Vehicule)
    if organisation_id:
        q_veh = q_veh.filter(Vehicule.organisation_id == organisation_id)

    for v in q_veh.all():
        if v.date_expiration_assurance and aujourdhui <= v.date_expiration_assurance <= seuil:
            alertes.append({
                "type": "ASSURANCE_EXPIRE_BIENTOT",
                "cible_type": "vehicule",
                "cible_id": v.id_bien,
                "organisation_id": v.organisation_id,
                "titre": f"Assurance bientôt expirée : {v.immatriculation or v.libelle}",
                "date_expiration": v.date_expiration_assurance.isoformat(),
                "jours_restants": (v.date_expiration_assurance - aujourdhui).days,
            })
        if v.date_expiration_visite_technique and aujourdhui <= v.date_expiration_visite_technique <= seuil:
            alertes.append({
                "type": "VISITE_TECHNIQUE_BIENTOT",
                "cible_type": "vehicule",
                "cible_id": v.id_bien,
                "organisation_id": v.organisation_id,
                "titre": f"Visite technique bientôt expirée : {v.immatriculation or v.libelle}",
                "date_expiration": v.date_expiration_visite_technique.isoformat(),
                "jours_restants": (v.date_expiration_visite_technique - aujourdhui).days,
            })
        if v.date_expiration_permis_transport and aujourdhui <= v.date_expiration_permis_transport <= seuil:
            alertes.append({
                "type": "PERMIS_TRANSPORT_BIENTOT",
                "cible_type": "vehicule",
                "cible_id": v.id_bien,
                "organisation_id": v.organisation_id,
                "titre": f"Permis de transport bientôt expiré : {v.immatriculation or v.libelle}",
                "date_expiration": v.date_expiration_permis_transport.isoformat(),
                "jours_restants": (v.date_expiration_permis_transport - aujourdhui).days,
            })

    return alertes