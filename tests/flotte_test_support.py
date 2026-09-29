from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import chauffeurs, vehicules
from app.core.database import get_db
from app.core.security import get_current_user


def flotte_client(factory, organisation_id: int, router=vehicules.router):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=organisation_id,
        organisation_id=organisation_id,
        role=SimpleNamespace(nom="ADMIN", id_role=1),
    )
    return TestClient(app)