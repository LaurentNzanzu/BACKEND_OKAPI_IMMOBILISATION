"""notification priorite and archive columns

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-13 22:00:00.000000

Ajoute :
- notifications.priorite (VARCHAR 20, défaut 'information')
- notification_user.est_archivee (BOOLEAN, défaut false)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "f9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _verify_post_migration(bind) -> None:
    """Vérifie que les données existantes ont les valeurs par défaut attendues."""
    invalid_priorite = bind.execute(
        text(
            "SELECT COUNT(*) FROM notifications "
            "WHERE priorite IS NULL OR priorite NOT IN ('information', 'importante', 'critique')"
        )
    ).scalar()
    if invalid_priorite and int(invalid_priorite) > 0:
        raise RuntimeError(
            f"Migration notifications.priorite : {invalid_priorite} ligne(s) invalide(s)"
        )

    null_archivee = bind.execute(
        text("SELECT COUNT(*) FROM notification_user WHERE est_archivee IS NULL")
    ).scalar()
    if null_archivee and int(null_archivee) > 0:
        raise RuntimeError(
            f"Migration notification_user.est_archivee : {null_archivee} NULL détecté(s)"
        )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    columns = {c["name"] for c in insp.get_columns("notifications")}
    if "priorite" not in columns:
        op.add_column(
            "notifications",
            sa.Column(
                "priorite",
                sa.String(length=20),
                server_default="information",
                nullable=False,
            ),
        )

    # Garantir les valeurs pour les lignes existantes
    op.execute(
        "UPDATE notifications SET priorite = 'information' "
        "WHERE priorite IS NULL OR priorite = ''"
    )

    insp = inspect(bind)
    nu_columns = {c["name"] for c in insp.get_columns("notification_user")}
    if "est_archivee" not in nu_columns:
        op.add_column(
            "notification_user",
            sa.Column(
                "est_archivee",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )

    op.execute(
        "UPDATE notification_user SET est_archivee = false WHERE est_archivee IS NULL"
    )

    _verify_post_migration(bind)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    nu_columns = {c["name"] for c in insp.get_columns("notification_user")}
    if "est_archivee" in nu_columns:
        op.drop_column("notification_user", "est_archivee")

    columns = {c["name"] for c in insp.get_columns("notifications")}
    if "priorite" in columns:
        op.drop_column("notifications", "priorite")
