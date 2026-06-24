from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from ..models.composant import Composant
from ..models.bien import Bien
from ..schemas.composant import ComposantCreate, ComposantUpdate, ComposantResponse

class ComposantService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _add_years(base_date: datetime, years: int) -> datetime:
        try:
            return base_date.replace(year=base_date.year + years)
        except ValueError:
            return base_date.replace(year=base_date.year + years, day=28)

    def get_effective_replacement_date(self, composant: Composant, bien: Optional[Bien] = None) -> Optional[datetime]:
        if composant.date_remplacement:
            return composant.date_remplacement

        ref = composant.date_mise_en_service
        if not ref and bien is not None:
            ref = getattr(bien, 'date_acquisition', None)

        if ref and composant.duree_vie_ans:
            return self._add_years(ref, composant.duree_vie_ans)
        return None

    def to_response(self, composant: Composant, bien: Optional[Bien] = None) -> ComposantResponse:
        data = ComposantResponse.model_validate(composant).model_dump()
        effective = self.get_effective_replacement_date(composant, bien)
        if effective:
            data['date_remplacement'] = effective
        return ComposantResponse(**data)

    def create_composant(self, data: ComposantCreate) -> Composant:
        bien = self.db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
        if not bien:
            raise ValueError(f"Bien {data.id_bien} non trouvé")

        payload = data.model_dump()
        if not payload.get('date_remplacement'):
            ref = payload.get('date_mise_en_service') or getattr(bien, 'date_acquisition', None)
            if ref and payload.get('duree_vie_ans'):
                payload['date_remplacement'] = self._add_years(ref, payload['duree_vie_ans'])

        composant = Composant(**payload)
        self.db.add(composant)
        self.db.commit()
        self.db.refresh(composant)
        return composant

    def get_composants_by_bien(self, id_bien: int) -> List[Composant]:
        return self.db.query(Composant).filter(Composant.id_bien == id_bien).all()

    def get_composant(self, id_composant: int) -> Optional[Composant]:
        return self.db.query(Composant).filter(Composant.id_composant == id_composant).first()

    def update_composant(self, id_composant: int, data: ComposantUpdate) -> Optional[Composant]:
        composant = self.get_composant(id_composant)
        if not composant:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(composant, field, value)
            
        self.db.commit()
        self.db.refresh(composant)
        return composant

    def delete_composant(self, id_composant: int) -> bool:
        composant = self.get_composant(id_composant)
        if not composant:
            return False
        self.db.delete(composant)
        self.db.commit()
        return True

    def get_valeur_totale_composants(self, id_bien: int) -> float:
        composants = self.get_composants_by_bien(id_bien)
        return sum(c.valeur for c in composants)

    def get_valeur_structure(self, id_bien: int) -> float:
        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        if not bien:
            return 0.0
        return float(bien.prix_acquisition) - self.get_valeur_totale_composants(id_bien)