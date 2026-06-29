from sqlalchemy.orm import Session
from typing import List, Optional
from ..models.localisation import Localisation
from ..schemas.localisation import LocalisationCreate


class LocalisationService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 500) -> List[Localisation]:
        return (
            self.db.query(Localisation)
            .order_by(Localisation.nom_localisation)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_id(self, id_localisation: int) -> Optional[Localisation]:
        return (
            self.db.query(Localisation)
            .filter(Localisation.id_localisation == id_localisation)
            .first()
        )

    def create(self, data: LocalisationCreate) -> Localisation:
        loc = Localisation(nom_localisation=data.nom_localisation.strip().upper())
        self.db.add(loc)
        self.db.commit()
        self.db.refresh(loc)
        return loc
