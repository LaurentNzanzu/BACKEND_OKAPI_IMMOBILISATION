"""Sprint 1 : Complétion des champs et statuts Flotte (Missions, Chauffeurs, Trajets, Véhicules)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 0. Notifications : valeurs Enum pour Flotte (PostgreSQL)
    if is_postgres:
        new_notification_types = [
            "MISSION_A_VALIDER",
            "MISSION_VALIDEE",
            "MISSION_REJETEE",
            "MISSION_DEMARREE",
            "MISSION_TERMINEE",
            "PERMIS_EXPIRE_BIENTOT",
            "ASSURANCE_EXPIRE_BIENTOT",
            "VISITE_TECHNIQUE_BIENTOT",
        ]
        for val in new_notification_types:
            op.execute(f"ALTER TYPE typenotificationenum ADD VALUE IF NOT EXISTS '{val}'")

    # 1. Missions : champs planification et suivi
    op.add_column("missions", sa.Column("numero_mission", sa.String(length=100), nullable=True))
    op.add_column("missions", sa.Column("passagers", sa.JSON(), server_default=sa.text("'[]'"), nullable=True))
    op.add_column("missions", sa.Column("km_depart", sa.Float(), nullable=True))
    op.add_column("missions", sa.Column("km_arrivee", sa.Float(), nullable=True))
    op.add_column("missions", sa.Column("heure_depart_reelle", sa.DateTime(), nullable=True))
    op.add_column("missions", sa.Column("heure_retour_reelle", sa.DateTime(), nullable=True))
    op.add_column("missions", sa.Column("observation", sa.Text(), nullable=True))
    op.add_column("missions", sa.Column("photo_depart_url", sa.String(length=500), nullable=True))
    op.add_column("missions", sa.Column("devise", sa.String(length=10), server_default="USD", nullable=False))

    op.create_index("ix_missions_numero_mission", "missions", ["numero_mission"])
    if is_postgres:
        op.create_index(
            "uq_mission_org_numero",
            "missions",
            ["organisation_id", "numero_mission"],
            unique=True,
            postgresql_where=sa.text("numero_mission IS NOT NULL"),
        )
    else:
        op.create_index(
            "uq_mission_org_numero",
            "missions",
            ["organisation_id", "numero_mission"],
            unique=True,
            sqlite_where=sa.text("numero_mission IS NOT NULL"),
        )

    # 2. Chauffeurs : statut, photo, embauche, observations, categorie_permis
    op.add_column("chauffeurs", sa.Column("categorie_permis", sa.String(length=50), nullable=True))
    op.add_column("chauffeurs", sa.Column("statut", sa.String(length=50), server_default="DISPONIBLE", nullable=False))
    op.add_column("chauffeurs", sa.Column("photo_url", sa.String(length=500), nullable=True))
    op.add_column("chauffeurs", sa.Column("date_embauche", sa.Date(), nullable=True))
    op.add_column("chauffeurs", sa.Column("observations", sa.Text(), nullable=True))

    # Migration des données type_permis -> categorie_permis si présent
    op.execute("UPDATE chauffeurs SET categorie_permis = type_permis WHERE categorie_permis IS NULL AND type_permis IS NOT NULL")
    op.execute("UPDATE chauffeurs SET statut = 'DISPONIBLE' WHERE disponible = true OR disponible IS NULL")
    op.execute("UPDATE chauffeurs SET statut = 'INDISPONIBLE' WHERE disponible = false")

    # 3. Trajets : géolocalisation, estimation carburant, source_donnees
    op.add_column("trajets", sa.Column("lat_depart", sa.Float(), nullable=True))
    op.add_column("trajets", sa.Column("lng_depart", sa.Float(), nullable=True))
    op.add_column("trajets", sa.Column("lat_arrivee", sa.Float(), nullable=True))
    op.add_column("trajets", sa.Column("lng_arrivee", sa.Float(), nullable=True))
    op.add_column("trajets", sa.Column("carburant_consomme_estime", sa.Float(), nullable=True))
    op.add_column("trajets", sa.Column("source_donnees", sa.String(length=50), server_default="MOBILE", nullable=False))

    # 4. Véhicules : caractéristiques techniques et administratives complètes
    op.add_column("vehicules", sa.Column("categorie", sa.String(length=50), server_default="VOITURE", nullable=True))
    op.add_column("vehicules", sa.Column("vin", sa.String(length=100), nullable=True))
    op.add_column("vehicules", sa.Column("numero_boitier_gps", sa.String(length=100), nullable=True))
    op.add_column("vehicules", sa.Column("date_expiration_assurance", sa.Date(), nullable=True))
    op.add_column("vehicules", sa.Column("date_expiration_visite_technique", sa.Date(), nullable=True))
    op.add_column("vehicules", sa.Column("date_expiration_permis_transport", sa.Date(), nullable=True))
    op.add_column("vehicules", sa.Column("capacite_reservoir", sa.Float(), nullable=True))
    op.add_column("vehicules", sa.Column("consommation_theorique", sa.Float(), nullable=True))
    op.add_column("vehicules", sa.Column("kilometrage_actuel", sa.Float(), server_default="0.0", nullable=False))
    op.add_column("vehicules", sa.Column("prochain_km_maintenance", sa.Float(), nullable=True))
    op.add_column("vehicules", sa.Column("couleur", sa.String(length=50), nullable=True))
    op.add_column("vehicules", sa.Column("nombre_places", sa.Integer(), nullable=True))

    # Migration type_vehicule -> categorie
    op.execute("UPDATE vehicules SET categorie = UPPER(type_vehicule) WHERE type_vehicule IS NOT NULL AND categorie IS NULL")


def downgrade() -> None:
    # 4. Véhicules
    op.drop_column("vehicules", "nombre_places")
    op.drop_column("vehicules", "couleur")
    op.drop_column("vehicules", "prochain_km_maintenance")
    op.drop_column("vehicules", "kilometrage_actuel")
    op.drop_column("vehicules", "consommation_theorique")
    op.drop_column("vehicules", "capacite_reservoir")
    op.drop_column("vehicules", "date_expiration_permis_transport")
    op.drop_column("vehicules", "date_expiration_visite_technique")
    op.drop_column("vehicules", "date_expiration_assurance")
    op.drop_column("vehicules", "numero_boitier_gps")
    op.drop_column("vehicules", "vin")
    op.drop_column("vehicules", "categorie")

    # 3. Trajets
    op.drop_column("trajets", "source_donnees")
    op.drop_column("trajets", "carburant_consomme_estime")
    op.drop_column("trajets", "lng_arrivee")
    op.drop_column("trajets", "lat_arrivee")
    op.drop_column("trajets", "lng_depart")
    op.drop_column("trajets", "lat_depart")

    # 2. Chauffeurs
    op.drop_column("chauffeurs", "observations")
    op.drop_column("chauffeurs", "date_embauche")
    op.drop_column("chauffeurs", "photo_url")
    op.drop_column("chauffeurs", "statut")
    op.drop_column("chauffeurs", "categorie_permis")

    # 1. Missions
    op.drop_index("uq_mission_org_numero", table_name="missions")
    op.drop_index("ix_missions_numero_mission", table_name="missions")
    op.drop_column("missions", "devise")
    op.drop_column("missions", "photo_depart_url")
    op.drop_column("missions", "observation")
    op.drop_column("missions", "heure_retour_reelle")
    op.drop_column("missions", "heure_depart_reelle")
    op.drop_column("missions", "km_arrivee")
    op.drop_column("missions", "km_depart")
    op.drop_column("missions", "passagers")
    op.drop_column("missions", "numero_mission")
