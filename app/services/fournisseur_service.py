# backend/app/services/fournisseur_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from ..models.fournisseur import Fournisseur
from ..schemas.fournisseur import FournisseurCreate, FournisseurUpdate

class FournisseurService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 100, search: Optional[str] = None) -> List[Fournisseur]:
        query = self.db.query(Fournisseur)
        if search:
            query = query.filter(Fournisseur.nom.ilike(f"%{search}%"))
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, fournisseur_id: int) -> Optional[Fournisseur]:
        return self.db.query(Fournisseur).filter(Fournisseur.id == fournisseur_id).first()

    def create(self, data: FournisseurCreate) -> Fournisseur:
        fournisseur = Fournisseur(**data.model_dump())
        self.db.add(fournisseur)
        self.db.commit()
        self.db.refresh(fournisseur)
        return fournisseur

    def update(self, fournisseur_id: int, data: FournisseurUpdate) -> Optional[Fournisseur]:
        fournisseur = self.get_by_id(fournisseur_id)
        if not fournisseur:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(fournisseur, key, value)
        self.db.commit()
        self.db.refresh(fournisseur)
        return fournisseur

    def delete(self, fournisseur_id: int) -> bool:
        fournisseur = self.get_by_id(fournisseur_id)
        if not fournisseur:
            return False
        self.db.delete(fournisseur)
        self.db.commit()
        return True