from app.core.database import Base
from app.models.trajet import Trajet
from app.services.trajet_service import list_trajets


def test_trajet_mouvement_foreign_key_uses_real_primary_key():
    foreign_key = next(iter(Base.metadata.tables["trajets"].c.mouvement_bien_id.foreign_keys))
    assert foreign_key.target_fullname == "mouvements_biens.id_mouvement"


def test_trajet_list_is_tenant_scoped(flotte_db):
    with flotte_db() as db:
        db.add_all([Trajet(organisation_id=1), Trajet(organisation_id=2)])
        db.commit()
        rows = list_trajets(db, organisation_id=1)
        assert len(rows) == 1
        assert rows[0].organisation_id == 1


def test_trajet_validation_rejects_inverted_km():
    import pytest
    from app.schemas.trajet import TrajetCreate
    with pytest.raises(ValueError, match="inférieur au kilométrage de début"):
        TrajetCreate(kilometrage_debut=100.0, kilometrage_fin=50.0)


def test_trajet_validation_rejects_inverted_dates():
    import pytest
    from datetime import datetime, timedelta
    from app.schemas.trajet import TrajetCreate
    now = datetime(2026, 10, 1, 10, 0)
    with pytest.raises(ValueError, match="antérieure à la date de début"):
        TrajetCreate(date_debut=now, date_fin=now - timedelta(hours=1))


def test_trajet_auto_calculates_distance_km(flotte_db):
    from app.schemas.trajet import TrajetCreate
    from app.services.trajet_service import create_trajet
    with flotte_db() as db:
        trajet = create_trajet(db, TrajetCreate(kilometrage_debut=1500.0, kilometrage_fin=1625.5), organisation_id=1)
        assert trajet.distance_km == 125.5
