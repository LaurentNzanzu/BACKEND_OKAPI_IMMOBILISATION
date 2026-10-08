"""Sprint 1 : Parc automobile, Chauffeurs, Missions, Affectations, Trajets

Revision ID: b1c2d3e4f5a6
Revises: a9420677808a
Create Date: 2026-10-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a9420677808a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 0. Extension pour anti-chevauchement GiST (PostgreSQL)
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    # 1. Table vehicules (héritage joint de biens)
    op.create_table(
        "vehicules",
        sa.Column("id_bien", sa.Integer(), nullable=False),
        sa.Column("type_vehicule", sa.String(length=100), nullable=True),
        sa.Column("marque", sa.String(length=100), nullable=True),
        sa.Column("modele", sa.String(length=100), nullable=True),
        sa.Column("immatriculation", sa.String(length=50), nullable=True),
        sa.Column("poids", sa.Float(), nullable=True),
        sa.Column("dimension", sa.String(length=100), nullable=True),
        sa.Column("type_carburant", sa.String(length=50), nullable=True),
        sa.Column("consommation_carburant", sa.Float(), nullable=True),
        sa.Column("consommation_huile", sa.Float(), nullable=True),
        sa.Column("type_propulsion", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["id_bien"], ["biens.id_bien"], name="fk_vehicules_bien", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_bien"),
    )
    op.create_index("ix_vehicules_immatriculation", "vehicules", ["immatriculation"])

    # 2. Table chauffeurs (avec utilisateur_id facultatif et index unique partiel)
    op.create_table(
        "chauffeurs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), nullable=True),
        sa.Column("nom", sa.String(length=100), nullable=False),
        sa.Column("prenom", sa.String(length=100), nullable=False),
        sa.Column("telephone", sa.String(length=50), nullable=True),
        sa.Column("numero_permis", sa.String(length=100), nullable=False),
        sa.Column("type_permis", sa.String(length=50), nullable=True),
        sa.Column("date_expiration_permis", sa.Date(), nullable=True),
        sa.Column("disponible", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.Column("actif", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.Column("date_creation", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], name="fk_chauffeurs_organisation"),
        sa.ForeignKeyConstraint(["utilisateur_id"], ["utilisateurs.id"], name="fk_chauffeurs_utilisateur", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chauffeurs_organisation_id", "chauffeurs", ["organisation_id"])
    op.create_index("ix_chauffeurs_utilisateur_id", "chauffeurs", ["utilisateur_id"])
    op.create_index("uq_chauffeurs_org_permis", "chauffeurs", ["organisation_id", "numero_permis"], unique=True)

    if is_postgres:
        op.create_index(
            "uq_chauffeur_org_user_actif",
            "chauffeurs",
            ["organisation_id", "utilisateur_id"],
            unique=True,
            postgresql_where=sa.text("utilisateur_id IS NOT NULL AND actif = true"),
        )

    # 3. Table missions (avec colonnes de cycle de workflow)
    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("projet_id", sa.Integer(), nullable=True),
        sa.Column("type_workflow", sa.String(length=50), server_default="MISSION", nullable=False),
        sa.Column("statut", sa.String(length=50), server_default="BROUILLON", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lieu_depart", sa.String(length=255), nullable=True),
        sa.Column("lieu_arrivee", sa.String(length=255), nullable=True),
        sa.Column("date_debut", sa.DateTime(), nullable=True),
        sa.Column("date_fin", sa.DateTime(), nullable=True),
        sa.Column("date_creation", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("cree_par", sa.Integer(), nullable=True),
        sa.Column("etape_actuelle_id", sa.Integer(), nullable=True),
        sa.Column("motif_rejet", sa.Text(), nullable=True),
        sa.Column("valide_par", sa.Integer(), nullable=True),
        sa.Column("date_validation", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], name="fk_missions_organisation"),
        sa.ForeignKeyConstraint(["projet_id"], ["projets.id"], name="fk_missions_projet"),
        sa.ForeignKeyConstraint(["cree_par"], ["utilisateurs.id"], name="fk_missions_cree_par"),
        sa.ForeignKeyConstraint(["etape_actuelle_id"], ["workflow_etapes.id"], name="fk_missions_etape", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["valide_par"], ["utilisateurs.id"], name="fk_missions_valide_par", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_missions_organisation_id", "missions", ["organisation_id"])
    op.create_index("ix_missions_projet_id", "missions", ["projet_id"])
    op.create_index("ix_missions_org_statut", "missions", ["organisation_id", "statut"])

    # 4. Table affectations_mission
    op.create_table(
        "affectations_mission",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=False),
        sa.Column("vehicule_id", sa.Integer(), nullable=True),
        sa.Column("chauffeur_id", sa.Integer(), nullable=True),
        sa.Column("date_debut", sa.DateTime(), nullable=False),
        sa.Column("date_fin", sa.DateTime(), nullable=False),
        sa.Column("statut", sa.String(length=50), server_default="PLANIFIEE", nullable=True),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], name="fk_affectations_organisation"),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], name="fk_affectations_mission", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicule_id"], ["vehicules.id_bien"], name="fk_affectations_vehicule"),
        sa.ForeignKeyConstraint(["chauffeur_id"], ["chauffeurs.id"], name="fk_affectations_chauffeur"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_affectations_mission_organisation_id", "affectations_mission", ["organisation_id"])
    op.create_index("ix_affectations_mission_mission_id", "affectations_mission", ["mission_id"])
    op.create_index("ix_affectations_mission_vehicule_id", "affectations_mission", ["vehicule_id"])
    op.create_index("ix_affectations_mission_chauffeur_id", "affectations_mission", ["chauffeur_id"])

    # Contraintes d'anti-chevauchement GiST (PostgreSQL uniquement)
    if is_postgres:
        op.execute("""
            ALTER TABLE affectations_mission ADD CONSTRAINT ex_affectation_vehicule_periode
            EXCLUDE USING gist (
                vehicule_id WITH =,
                tsrange(date_debut, date_fin) WITH &&
            ) WHERE (vehicule_id IS NOT NULL AND statut IS DISTINCT FROM 'ANNULEE' AND statut IS DISTINCT FROM 'REJETEE');
        """)
        op.execute("""
            ALTER TABLE affectations_mission ADD CONSTRAINT ex_affectation_chauffeur_periode
            EXCLUDE USING gist (
                chauffeur_id WITH =,
                tsrange(date_debut, date_fin) WITH &&
            ) WHERE (chauffeur_id IS NOT NULL AND statut IS DISTINCT FROM 'ANNULEE' AND statut IS DISTINCT FROM 'REJETEE');
        """)

    # 5. Table trajets
    op.create_table(
        "trajets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=True),
        sa.Column("mouvement_bien_id", sa.Integer(), nullable=True),
        sa.Column("vehicule_id", sa.Integer(), nullable=True),
        sa.Column("chauffeur_id", sa.Integer(), nullable=True),
        sa.Column("date_debut", sa.DateTime(), nullable=True),
        sa.Column("date_fin", sa.DateTime(), nullable=True),
        sa.Column("kilometrage_debut", sa.Float(), nullable=True),
        sa.Column("kilometrage_fin", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("statut", sa.String(length=50), server_default="EN_COURS", nullable=True),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], name="fk_trajets_organisation"),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], name="fk_trajets_mission", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mouvement_bien_id"], ["mouvements_biens.id_mouvement"], name="fk_trajets_mouvement"),
        sa.ForeignKeyConstraint(["vehicule_id"], ["vehicules.id_bien"], name="fk_trajets_vehicule"),
        sa.ForeignKeyConstraint(["chauffeur_id"], ["chauffeurs.id"], name="fk_trajets_chauffeur"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trajets_organisation_id", "trajets", ["organisation_id"])
    op.create_index("ix_trajets_mission_id", "trajets", ["mission_id"])

    # 6. TypeBien 'VEHICULE' par défaut si absent
    op.execute("""
        INSERT INTO types_biens (libelle, code, compte_comptable, description, est_actif)
        SELECT 'Véhicule', 'VEHICULE', '2450', 'Matériel de transport (flotte)', true
        WHERE NOT EXISTS (SELECT 1 FROM types_biens WHERE code = 'VEHICULE');
    """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("ALTER TABLE affectations_mission DROP CONSTRAINT IF EXISTS ex_affectation_chauffeur_periode;")
        op.execute("ALTER TABLE affectations_mission DROP CONSTRAINT IF EXISTS ex_affectation_vehicule_periode;")

    op.drop_table("trajets")
    op.drop_table("affectations_mission")
    op.drop_table("missions")
    op.drop_table("chauffeurs")
    op.drop_table("vehicules")
