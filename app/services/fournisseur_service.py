# backend/app/services/fournisseur_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from ..models.fournisseur import Fournisseur
from ..schemas.fournisseur import FournisseurCreate, FournisseurUpdate

class FournisseurService:
    def __init__(self, db: Session):
        self.db = db

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_all(self, skip: int = 0, limit: int = 100, search: Optional[str] = None, organisation_id: Optional[int] = None) -> List[Fournisseur]:
        query = self.db.query(Fournisseur)
        if organisation_id is not None:
            query = query.filter(Fournisseur.organisation_id == organisation_id)
        if search:
            query = query.filter(Fournisseur.nom.ilike(f"%{search}%"))
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, fournisseur_id: int, organisation_id: Optional[int] = None) -> Optional[Fournisseur]:
        query = self.db.query(Fournisseur).filter(Fournisseur.id == fournisseur_id)
        if organisation_id is not None:
            query = query.filter(Fournisseur.organisation_id == organisation_id)
        return query.first()

    def create(self, data: FournisseurCreate, organisation_id: Optional[int] = None) -> Fournisseur:
        payload = data.model_dump()
        # ═══ 5.22 — Injection organisation_id ═══
        if organisation_id is not None:
            payload["organisation_id"] = organisation_id
        # ═══ FIN 5.22 ═══
        fournisseur = Fournisseur(**payload)
        self.db.add(fournisseur)
        self.db.commit()
        self.db.refresh(fournisseur)
        return fournisseur

    def update(self, fournisseur_id: int, data: FournisseurUpdate, organisation_id: Optional[int] = None) -> Optional[Fournisseur]:
        fournisseur = self.get_by_id(fournisseur_id, organisation_id=organisation_id)
        if not fournisseur:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(fournisseur, key, value)
        self.db.commit()
        self.db.refresh(fournisseur)
        return fournisseur

    def delete(self, fournisseur_id: int, organisation_id: Optional[int] = None) -> bool:
        fournisseur = self.get_by_id(fournisseur_id, organisation_id=organisation_id)
        if not fournisseur:
            return False
        self.db.delete(fournisseur)
        self.db.commit()
        return True
    # ═══ FIN MODIF 5.22 ═══