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
            caisse = Caisse(solde_physique=0.0, solde_theorique=0.0, devise="USD", statut="ACTIF")
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

    def ordonner_mouvement_caisse(
        self,
        type_mouvement: str,  # 'ENTREE' ou 'SORTIE'
        montant: float,
        origine_type: str,    # 'BESOIN', 'MAINTENANCE', 'STOCK', 'ACQUISITION', 'CESSION', 'AMORTISSEMENT'
        origine_id: int,
        motif: str,
        beneficiaire: str = None,
        mode_reglement: str = 'ESPECES'
    ) -> dict:
        """
        Fonction centrale qui orchestre un mouvement de caisse.
        - Vérifie le solde si SORTIE
        - Crée le mouvement
        - Génère le PDF (BEC ou BSC)
        - Met à jour le solde
        - Retourne le mouvement créé
        """
        from .mouvement_caisse_service import MouvementCaisseService
        from ..schemas.mouvement_caisse import MouvementCaisseCreate
        
        caisse = self.get_caisse_principale()
        if not caisse:
            caisse = Caisse(solde_physique=0.0, solde_theorique=0.0, devise="USD", statut="ACTIF")
            self.db.add(caisse)
            self.db.commit()
            self.db.refresh(caisse)

        mvt_create = MouvementCaisseCreate(
            id_caisse=caisse.id_caisse,
            type_mouvement=type_mouvement,
            montant=montant,
            motif=motif,
            origine_type=origine_type,
            origine_id=origine_id,
            mode_reglement=mode_reglement,
            beneficiaire=beneficiaire
        )
        
        mvt_service = MouvementCaisseService(self.db)
        mvt = mvt_service.creer_mouvement(mvt_create)
        
        if type_mouvement == "SORTIE" and caisse.solde_physique < montant:
            mvt.statut = "EN_ATTENTE_FONDS"
            self.db.commit()
            return {"success": False, "mouvement": mvt, "message": "Solde insuffisant"}
            
        if type_mouvement == "SORTIE":
            caisse.solde_physique -= montant
            caisse.solde_theorique -= montant
        else:
            caisse.solde_physique += montant
            caisse.solde_theorique += montant
            
        mvt.statut = "VALIDE"
        mvt.date_validation = datetime.utcnow()
        if mvt.piece_justificative:
            mvt.piece_justificative.signature_caissier = True
            mvt.piece_justificative.date_signature_caissier = datetime.utcnow()
            
        pdf_url = mvt_service.generer_pdf_mouvement(mvt)
        mvt.piece_jointe_url = pdf_url
        if mvt.piece_justificative:
            mvt.piece_justificative.url_fichier = pdf_url
            
        self.db.commit()
        return {"success": True, "mouvement": mvt}
