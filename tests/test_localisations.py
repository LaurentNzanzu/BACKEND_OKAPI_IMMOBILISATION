"""Localisation creation tested with an isolated SQLite database."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import Base
from app.models.localisation import Localisation
from app.schemas.localisation import LocalisationCreate
from app.services.localisation_service import LocalisationService


@pytest.fixture
def service():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Localisation.__table__])
    with Session(engine) as db:
        yield LocalisationService(db)
    engine.dispose()


def test_normalization_and_duplicate_reuse(service):
    first = service.create(LocalisationCreate(nom_localisation="  Bureau   DG  "), 1)
    second = service.create(LocalisationCreate(nom_localisation="bureau dg"), 1)
    assert first.nom_localisation == "BUREAU DG"
    assert first.id_localisation == second.id_localisation
    assert service.db.query(Localisation).count() == 1


def test_same_name_allowed_in_two_organisations(service):
    data = LocalisationCreate(nom_localisation="Bureau DG")
    first = service.create(data, 1)
    second = service.create(data, 2)
    assert first.id_localisation != second.id_localisation
    assert second.organisation_id == 2


def test_legacy_spacing_and_case_are_reused(service):
    legacy = Localisation(nom_localisation=" Bureau  dg ", organisation_id=1)
    service.db.add(legacy)
    service.db.commit()
    result = service.create(LocalisationCreate(nom_localisation="bureau dg"), 1)
    assert result.id_localisation == legacy.id_localisation


@pytest.mark.parametrize("name", ["", "   \t\n", "A" * 201])
def test_invalid_name_rejected(name):
    with pytest.raises(ValidationError):
        LocalisationCreate(nom_localisation=name)
