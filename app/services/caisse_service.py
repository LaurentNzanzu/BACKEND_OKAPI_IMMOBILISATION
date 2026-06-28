# backend/app/services/caisse_service.py
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from ..models.caisse import Caisse
from ..schemas.caisse import CaisseCreate, CaisseUpdate


class CaisseService:
    def __init__(self, db: Session):
        self.db = db

    def get_caisse_principale(self) -> Optional[Caisse]:
        """Récupère la caisse principale (ou la première caisse active)."""
        return self.db.query(Caisse).filter(Caisse.statut == "ACTIF").first()

    def verifier_tresorerie(self, montant: float) -> dict:
        """
        Vérifie si la trésorerie physique disponible en caisse est suffisante.
        Condition : caisse.solde_physique >= montant
        """
        caisse = self.get_caisse_principale()
        if not caisse:
            # Si aucune caisse n'existe en BDD, créer une caisse par défaut avec 0.0
            caisse = Caisse(solde_physique=0.0, solde_theorique=0.0, devise="FCFA", statut="ACTIF")
            self.db.add(caisse)
            self.db.commit()
            self.db.refresh(caisse)

        solde = float(caisse.solde_physique)
        est_suffisante = solde >= montant

        if est_suffisante:
            message = f"Fonds suffisants en caisse. Solde disponible: {solde:,.2f} {caisse.devise}."
        else:
            message = f"Fonds caisse Insuffisant. Solde disponible: {solde:,.2f} {caisse.devise}, Montant demandé: {montant:,.2f} {caisse.devise}."

        return {
            "est_suffisante": est_suffisante,
            "solde_disponible": solde,
            "message": message
        }

    def lister_caisses(self) -> List[Caisse]:
        return self.db.query(Caisse).all()

    def obtenir_caisse(self, id_caisse: int) -> Optional[Caisse]:
        return self.db.query(Caisse).filter(Caisse.id_caisse == id_caisse).first()

    def creer_caisse(self, data: CaisseCreate) -> Caisse:
        caisse = Caisse(**data.model_dump())
        self.db.add(caisse)
        self.db.commit()
        self.db.refresh(caisse)
        return caisse

    def mettre_a_jour_caisse(self, id_caisse: int, data: CaisseUpdate) -> Optional[Caisse]:
        caisse = self.obtenir_caisse(id_caisse)
        if not caisse:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, val in update_data.items():
            setattr(caisse, field, val)

        self.db.commit()
        self.db.refresh(caisse)
        return caisse

    def effectuer_rapprochement(self, id_caisse: int, solde_physique_constate: float) -> Optional[Caisse]:
        caisse = self.obtenir_caisse(id_caisse)
        if not caisse:
            return None

        caisse.solde_physique = solde_physique_constate
        caisse.dernier_rapprochement = datetime.utcnow()
        self.db.commit()
        self.db.refresh(caisse)
        return caisse
