from sqlalchemy.orm import Session
from typing import List, Optional
from ..models.localisation import Localisation
from ..schemas.localisation import LocalisationCreate


class LocalisationService:
    def __init__(self, db: Session):
        self.db = db

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_all(self, skip: int = 0, limit: int = 500, organisation_id: Optional[int] = None) -> List[Localisation]:
        query = self.db.query(Localisation)
        if organisation_id is not None:
            query = query.filter(Localisation.organisation_id == organisation_id)
        return (
            query
            .order_by(Localisation.nom_localisation)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_id(self, id_localisation: int, organisation_id: Optional[int] = None) -> Optional[Localisation]:
        query = (
            self.db.query(Localisation)
            .filter(Localisation.id_localisation == id_localisation)
        )
        if organisation_id is not None:
            query = query.filter(Localisation.organisation_id == organisation_id)
        return query.first()

    def create(self, data: LocalisationCreate, organisation_id: Optional[int] = None) -> Localisation:
        loc = Localisation(
            nom_localisation=data.nom_localisation.strip().upper(),
            organisation_id=organisation_id,   # ═══ 5.22 — AJOUT ═══
        )
        self.db.add(loc)
        self.db.commit()
        self.db.refresh(loc)
        return loc
    # ═══ FIN MODIF 5.22 ═══