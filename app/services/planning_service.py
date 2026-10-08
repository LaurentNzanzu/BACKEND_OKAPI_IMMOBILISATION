from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.affectation_mission import AffectationMission
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.models.mission import Mission
from app.models.maintenance import Maintenance, StatutMaintenance


def get_planning(
    db: Session,
    organisation_id: int,
    date_debut: datetime,
    date_fin: datetime,
):
    """Retourne les affectations actives et planifiées sur la période."""
    return (
        db.query(AffectationMission)
        .filter(
            AffectationMission.organisation_id == organisation_id,
            AffectationMission.date_debut < date_fin,
            AffectationMission.date_fin > date_debut,
            ~AffectationMission.statut.in_(["ANNULEE", "REJETEE"]),
        )
        .all()
    )


def get_gantt_planning(
    db: Session,
    organisation_id: int,
    date_debut: datetime,
    date_fin: datetime,
) -> dict:
    """
    Retourne la matrice complète pour la vue Gantt (véhicules × jours) :
    - Liste des véhicules avec statut et caractéristiques
    - Liste des chauffeurs disponibles/actifs
    - Affectations de missions avec détails
    - Maintenances planifiées sur la période
    """
    vehicules = (
        db.query(Vehicule)
        .filter(Vehicule.organisation_id == organisation_id)
        .all()
    )
    chauffeurs = (
        db.query(Chauffeur)
        .filter(Chauffeur.organisation_id == organisation_id, Chauffeur.actif == True)
        .all()
    )
    affectations = (
        db.query(AffectationMission)
        .filter(
            AffectationMission.organisation_id == organisation_id,
            AffectationMission.date_debut < date_fin,
            AffectationMission.date_fin > date_debut,
            ~AffectationMission.statut.in_(["ANNULEE", "REJETEE"]),
        )
        .all()
    )
    maintenances = (
        db.query(Maintenance)
        .filter(
            Maintenance.organisation_id == organisation_id,
            ~Maintenance.statut.in_([StatutMaintenance.TERMINEE, StatutMaintenance.ANNULEE]),
        )
        .all()
    )

    # Filtrer maintenances sur la période
    maintenances_periode = []
    for m in maintenances:
        m_deb = m.date_debut_reelle or m.date_planifiee
        m_fin = m.date_fin_reelle or (m_deb + timedelta(days=1) if m_deb else None)
        if m_deb and m_fin and m_deb < date_fin and m_fin > date_debut:
            maintenances_periode.append({
                "id_maintenance": m.id_maintenance,
                "id_bien": m.id_bien,
                "titre": m.titre or "Maintenance",
                "type": getattr(m.type_maintenance, "value", str(m.type_maintenance)),
                "statut": getattr(m.statut, "value", str(m.statut)),
                "date_debut": m_deb.isoformat() if hasattr(m_deb, "isoformat") else str(m_deb),
                "date_fin": m_fin.isoformat() if hasattr(m_fin, "isoformat") else str(m_fin),
                "bloquant": True,
            })

    return {
        "periode": {
            "date_debut": date_debut.isoformat(),
            "date_fin": date_fin.isoformat(),
        },
        "vehicules": [
            {
                "id_bien": v.id_bien,
                "immatriculation": v.immatriculation,
                "designation": getattr(v, "designation", None) or getattr(v, "libelle", None) or f"{v.marque or ''} {v.modele or ''}".strip(),
                "marque": v.marque,
                "modele": v.modele,
                "categorie": v.categorie,
                "kilometrage_actuel": v.kilometrage_actuel,
                "couleur": v.couleur,
                "nombre_places": v.nombre_places,
                "etat": getattr(v.etat, "value", str(v.etat)) if getattr(v, "etat", None) else "BON",
            }
            for v in vehicules
        ],
        "chauffeurs": [
            {
                "id": c.id,
                "nom": c.nom,
                "prenom": c.prenom,
                "telephone": c.telephone,
                "categorie_permis": c.categorie_permis,
                "statut": c.statut,
                "disponible": c.disponible,
            }
            for c in chauffeurs
        ],
        "affectations": [
            {
                "id": a.id,
                "mission_id": a.mission_id,
                "vehicule_id": a.vehicule_id,
                "chauffeur_id": a.chauffeur_id,
                "date_debut": a.date_debut.isoformat() if a.date_debut else None,
                "date_fin": a.date_fin.isoformat() if a.date_fin else None,
                "statut": a.statut,
                "commentaire": a.commentaire,
                "mission": {
                    "id": a.mission.id,
                    "numero_mission": a.mission.numero_mission,
                    "motif": a.mission.destination or a.mission.description,
                    "destination": a.mission.destination,
                    "statut": a.mission.statut,
                } if a.mission else None,
                "chauffeur": f"{a.chauffeur.prenom} {a.chauffeur.nom}" if a.chauffeur else None,
            }
            for a in affectations
        ],
        "maintenances": maintenances_periode,
    }