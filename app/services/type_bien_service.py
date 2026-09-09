# backend/app/services/type_bien_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models.type_bien import TypeBien
from ..models.bien import Bien
from ..schemas.type_bien import TypeBienCreate, TypeBienUpdate
import logging

logger = logging.getLogger(__name__)


class TypeBienService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(
        self,
            skip: int = 0,
            limit: int = 100,
            est_actif: Optional[bool] = None,
            search: Optional[str] = None
        ) -> List[TypeBien]:
            """Récupère tous les types de biens avec filtres."""
            query = self.db.query(TypeBien)

            if est_actif is not None:
                query = query.filter(TypeBien.est_actif == est_actif)

            if search:
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        TypeBien.libelle.ilike(term),
                        TypeBien.code.ilike(term)
                    )
                )

            # ✅ CORRECTION : order_by() AVANT offset() et limit()
            return (
                query
                .order_by(TypeBien.libelle)  # ← D'ABORD le tri
                .offset(skip)                # ← ENSUITE le décalage
                .limit(limit)                # ← ENFIN la limite
                .all()
            )
    def get_count(
        self,
        est_actif: Optional[bool] = None,
        search: Optional[str] = None
    ) -> int:
        """Compte le nombre de types de biens avec filtres."""
        query = self.db.query(func.count(TypeBien.id))

        if est_actif is not None:
            query = query.filter(TypeBien.est_actif == est_actif)

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    TypeBien.libelle.ilike(term),
                    TypeBien.code.ilike(term)
                )
            )

        return query.scalar() or 0

    def get_by_id(self, type_id: int) -> Optional[TypeBien]:
        """Récupère un type de bien par son ID."""
        return self.db.query(TypeBien).filter(TypeBien.id == type_id).first()

    def get_by_code(self, code: str) -> Optional[TypeBien]:
        """Récupère un type de bien par son code."""
        return self.db.query(TypeBien).filter(TypeBien.code == code).first()

    def create(self, data: TypeBienCreate) -> TypeBien:
        """Crée un nouveau type de bien."""
        # Vérifier si le code existe déjà
        existing = self.get_by_code(data.code)
        if existing:
            raise ValueError(f"Un type de bien avec le code '{data.code}' existe déjà")

        # Vérifier si le libellé existe déjà
        existing = self.db.query(TypeBien).filter(TypeBien.libelle == data.libelle).first()
        if existing:
            raise ValueError(f"Un type de bien avec le libellé '{data.libelle}' existe déjà")

        type_bien = TypeBien(
            libelle=data.libelle,
            code=data.code,
            compte_comptable=data.compte_comptable,
            champs_specifiques=data.champs_specifiques or [],
            description=data.description,
            est_actif=data.est_actif,
            date_creation=datetime.utcnow(),
            date_modification=datetime.utcnow()
        )

        self.db.add(type_bien)
        self.db.commit()
        self.db.refresh(type_bien)

        return type_bien

    def update(self, type_id: int, data: TypeBienUpdate) -> TypeBien:
        """Met à jour un type de bien."""
        type_bien = self.get_by_id(type_id)
        if not type_bien:
            raise ValueError("Type de bien non trouvé")

        update_data = data.model_dump(exclude_unset=True)

        # Vérifier si le nouveau code est déjà utilisé
        if "code" in update_data and update_data["code"] != type_bien.code:
            existing = self.get_by_code(update_data["code"])
            if existing:
                raise ValueError(f"Un type de bien avec le code '{update_data['code']}' existe déjà")

        # Vérifier si le nouveau libellé est déjà utilisé
        if "libelle" in update_data and update_data["libelle"] != type_bien.libelle:
            existing = self.db.query(TypeBien).filter(TypeBien.libelle == update_data["libelle"]).first()
            if existing:
                raise ValueError(f"Un type de bien avec le libellé '{update_data['libelle']}' existe déjà")

        for field, value in update_data.items():
            if field == "champs_specifiques" and value is not None:
                # Valider les champs avant de les sauvegarder
                for champ in value:
                    if not isinstance(champ, dict):
                        raise ValueError("Chaque champ doit être un dictionnaire")
                    if 'nom' not in champ or 'type' not in champ:
                        raise ValueError("Chaque champ doit avoir 'nom' et 'type'")
                setattr(type_bien, field, value)
            elif value is not None:
                setattr(type_bien, field, value)

        type_bien.date_modification = datetime.utcnow()
        self.db.commit()
        self.db.refresh(type_bien)

        return type_bien

    def delete(self, type_id: int) -> bool:
        """
        Supprime un type de bien (désactivation).
        Vérifie d'abord qu'il n'est pas utilisé.
        """
        type_bien = self.get_by_id(type_id)
        if not type_bien:
            raise ValueError("Type de bien non trouvé")

        # Vérifier si le type est utilisé
        if self.is_used_by_biens(type_id):
            raise ValueError("Ce type de bien est utilisé par des biens existants")

        # Suppression logique
        type_bien.est_actif = False
        type_bien.date_modification = datetime.utcnow()
        self.db.commit()

        return True

    def is_used_by_biens(self, type_id: int) -> bool:
        """Vérifie si un type de bien est utilisé par des biens."""
        count = self.db.query(func.count(Bien.id_bien)).filter(
            Bien.id_type_bien == type_id
        ).scalar()
        return count > 0

    def ajouter_champ(self, type_id: int, champ: Dict[str, Any]) -> TypeBien:
        """Ajoute un champ spécifique à un type de bien."""
        type_bien = self.get_by_id(type_id)
        if not type_bien:
            raise ValueError("Type de bien non trouvé")

        # Valider le champ
        if 'nom' not in champ or 'type' not in champ:
            raise ValueError("Le champ doit avoir 'nom' et 'type'")

        champs = type_bien.champs_specifiques or []
        
        # Vérifier si le champ existe déjà
        for c in champs:
            if c.get('nom') == champ['nom']:
                raise ValueError(f"Le champ '{champ['nom']}' existe déjà")

        champs.append(champ)
        type_bien.champs_specifiques = champs
        type_bien.date_modification = datetime.utcnow()

        self.db.commit()
        self.db.refresh(type_bien)

        return type_bien

    def supprimer_champ(self, type_id: int, champ_nom: str) -> TypeBien:
        """Supprime un champ spécifique d'un type de bien."""
        type_bien = self.get_by_id(type_id)
        if not type_bien:
            raise ValueError("Type de bien non trouvé")

        champs = type_bien.champs_specifiques or []
        
        # Vérifier si le champ existe
        champ_trouve = False
        new_champs = []
        for c in champs:
            if c.get('nom') == champ_nom:
                champ_trouve = True
                continue
            new_champs.append(c)

        if not champ_trouve:
            raise ValueError(f"Le champ '{champ_nom}' n'existe pas")

        type_bien.champs_specifiques = new_champs
        type_bien.date_modification = datetime.utcnow()

        self.db.commit()
        self.db.refresh(type_bien)

        return type_bien