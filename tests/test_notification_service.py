"""Tests unitaires — notifications (filtres, priorité, archivage)."""
import sys
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.notification import TypeNotificationEnum  # noqa: E402
from app.services.notification_service import (  # noqa: E402
    _default_priorite_for_type,
    _serialize_notification,
)


def test_default_priorite_critique_for_stock_alerts():
    assert _default_priorite_for_type(TypeNotificationEnum.ALERTE_STOCK) == "critique"
    assert _default_priorite_for_type(TypeNotificationEnum.STOCK_INSUFFISANT) == "critique"


def test_default_priorite_importante_for_besoin():
    assert _default_priorite_for_type(TypeNotificationEnum.BESOIN_CREE) == "importante"


def test_default_priorite_information_for_other():
    assert _default_priorite_for_type(TypeNotificationEnum.PANNE_RESOLUE) == "information"


def test_serialize_notification_includes_user_state():
    notif = SimpleNamespace(
        id_notification=1,
        type_notification=TypeNotificationEnum.BESOIN_CREE,
        titre="Test",
        contenu="Contenu",
        lien_action="/besoins/1",
        date_creation=datetime.now(timezone.utc),
        priorite="importante",
    )
    data = _serialize_notification(notif, est_lu=False, est_archivee=False)
    assert data["id_notification"] == 1
    assert data["priorite"] == "importante"
    assert data["est_lu"] is False
    assert data["est_archivee"] is False


def test_serialize_notification_defaults_priorite_information():
    notif = SimpleNamespace(
        id_notification=2,
        type_notification=TypeNotificationEnum.MOUVEMENT_CREE,
        titre="Mouvement",
        contenu="OK",
        lien_action=None,
        date_creation=datetime.now(timezone.utc),
        priorite=None,
    )
    data = _serialize_notification(notif)
    assert data["priorite"] == "information"
