import pytest

from app.models.projet import Projet
from app.schemas.mission import MissionCreate
from app.services.mission_service import create_mission


def test_mission_rejects_project_from_another_organisation(flotte_db):
    with flotte_db() as db:
        project = Projet(organisation_id=2, code="OTHER", nom="Other tenant")
        db.add(project)
        db.commit()
        project_id = project.id
        with pytest.raises(ValueError, match="cette organisation"):
            create_mission(db, MissionCreate(projet_id=project_id), organisation_id=1)


def test_mission_without_project_is_allowed(flotte_db):
    with flotte_db() as db:
        mission = create_mission(db, MissionCreate(), organisation_id=1)
        assert mission.organisation_id == 1
        assert mission.projet_id is None