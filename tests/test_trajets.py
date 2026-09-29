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