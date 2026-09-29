import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models
from app.core.database import Base
from app.models.localisation import Localisation
from app.models.organisation import Organisation
from app.models.type_bien import TypeBien


@pytest.fixture
def flotte_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        for org_id in (1, 2):
            db.add(Organisation(
                id=org_id,
                nom=f"Organisation {org_id}",
                code=f"ORG{org_id}",
                email_admin=f"admin{org_id}@example.test",
                quota_vehicules=10,
                quota_chauffeurs=10,
                quota_missions_mois=10,
                parametres_json={"modules_actifs": ["VEHICULE", "CHAUFFEUR", "MISSION", "TRAJET"]},
            ))
        db.add(TypeBien(libelle="Véhicule", code="VEHICULE"))
        db.flush()
        for org_id in (1, 2):
            db.add(Localisation(
                id_localisation=org_id,
                organisation_id=org_id,
                nom_localisation=f"Dépôt {org_id}",
            ))
        db.commit()
    try:
        yield factory
    finally:
        engine.dispose()