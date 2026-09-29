from sqlalchemy.orm import Session
from app.models.mission import Mission
from app.services.workflow_service import WorkflowService


class MissionWorkflowService:
    @staticmethod
    def transition(db: Session, mission_id: int, action: str, organisation_id: int, user_id: int):
        mission = (
            db.query(Mission)
            .filter(Mission.id == mission_id, Mission.organisation_id == organisation_id)
            .first()
        )
        if not mission:
            raise ValueError("Mission introuvable")

        # TODO: expose a generic transition() method in WorkflowService.
        raise NotImplementedError(
            "WorkflowService ne fournit pas encore de méthode de transition générique"
        )