# backend/app/services/mouvement_caisse_service.py
import os
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Optional

from ..models.mouvement_caisse import MouvementCaisse
from ..models.caisse import Caisse
from ..models.piece_justificative import PieceJustificative
from ..models.utilisateur import Utilisateur
from ..schemas.mouvement_caisse import MouvementCaisseCreate
from ..utils.pdf_generator import generer_bec_pdf, generer_bsc_pdf


class MouvementCaisseService:
    def __init__(self, db: Session):
        self.db = db

    def creer_mouvement(self, data: MouvementCaisseCreate) -> MouvementCaisse:
        caisse = self.db.query(Caisse).filter(Caisse.id_caisse == data.id_caisse).first()
        if not caisse:
            raise ValueError("Caisse non trouvée")

        solde_avant = caisse.solde_physique

        if data.type_mouvement == "SORTIE":
            if caisse.solde_physique < data.montant:
                # Si fonds insuffisants, on crée quand même le mouvement en statut 'BROUILLON' ou 'EN_ATTENTE_FONDS'
                # Mais on lèvera une erreur si l'on tente de valider
                pass
            solde_apres = solde_avant - data.montant
        else:
            solde_apres = solde_avant + data.montant

        # Générer le numéro de pièce séquentiel
        year = datetime.utcnow().year
        count = self.db.query(MouvementCaisse).filter(
            MouvementCaisse.date_mouvement >= datetime(year, 1, 1),
            MouvementCaisse.date_mouvement < datetime(year + 1, 1, 1)
        ).count()
        seq = count + 1
        prefix = "BEC" if data.type_mouvement == "ENTREE" else "BSC"
        numero_piece = f"{prefix}-{year}-{seq:04d}"

        mouvement = MouvementCaisse(
            id_caisse=data.id_caisse,
            numero_piece=numero_piece,
            type_mouvement=data.type_mouvement,
            montant=data.montant,
            solde_avant=solde_avant,
            solde_apres=solde_apres,
            motif=data.motif,
            origine_type=data.origine_type,
            origine_id=data.origine_id,
            mode_reglement=data.mode_reglement or "ESPECES",
            beneficiaire=data.beneficiaire,
            statut="BROUILLON"
        )
        self.db.add(mouvement)
        self.db.flush()

        # Générer immédiatement le PDF associé
        pdf_url = self.generer_pdf_mouvement(mouvement)
        mouvement.piece_jointe_url = pdf_url

        # Créer la pièce justificative associée
        piece = PieceJustificative(
            id_mouvement=mouvement.id_mouvement,
            type_document=prefix,
            numero_document=numero_piece,
            url_fichier=pdf_url
        )
        self.db.add(piece)
        self.db.flush()

        return mouvement

    def valider_mouvement(self, id_mouvement: int, valide_par_id: int) -> MouvementCaisse:
        mouvement = self.db.query(MouvementCaisse).filter(MouvementCaisse.id_mouvement == id_mouvement).first()
        if not mouvement:
            raise ValueError("Mouvement non trouvé")

        if mouvement.statut == "VALIDE":
            return mouvement

        caisse = self.db.query(Caisse).filter(Caisse.id_caisse == mouvement.id_caisse).first()
        if not caisse:
            raise ValueError("Caisse non trouvée")

        if mouvement.type_mouvement == "SORTIE":
            # RÈGLE D'OR : CONTRAINTE DE NON-NÉGATIVITÉ
            if caisse.solde_physique < mouvement.montant:
                mouvement.statut = "EN_ATTENTE_FONDS"
                self.db.commit()
                raise ValueError(f"Solde caisse insuffisant. Solde disponible: {caisse.solde_physique} USD.")
            
            caisse.solde_physique -= mouvement.montant
            caisse.solde_theorique -= mouvement.montant
        else:
            caisse.solde_physique += mouvement.montant
            caisse.solde_theorique += mouvement.montant

        mouvement.statut = "VALIDE"
        mouvement.valide_par = valide_par_id
        mouvement.date_validation = datetime.utcnow()

        # Signer numériquement en tant que caissier
        if mouvement.piece_justificative:
            mouvement.piece_justificative.signature_caissier = True
            mouvement.piece_justificative.date_signature_caissier = datetime.utcnow()

        self.db.flush()

        # Régénérer le PDF avec les signatures mises à jour
        pdf_url = self.generer_pdf_mouvement(mouvement)
        mouvement.piece_jointe_url = pdf_url
        if mouvement.piece_justificative:
            mouvement.piece_justificative.url_fichier = pdf_url

        self.db.commit()
        return mouvement

    def signer_dg(self, id_mouvement: int, approuve: bool, motif: Optional[str] = None) -> MouvementCaisse:
        mouvement = self.db.query(MouvementCaisse).filter(MouvementCaisse.id_mouvement == id_mouvement).first()
        if not mouvement:
            raise ValueError("Mouvement non trouvé")

        if approuve:
            if mouvement.piece_justificative:
                mouvement.piece_justificative.signature_dg = True
                mouvement.piece_justificative.date_signature_dg = datetime.utcnow()
            
            # Si déjà validé par le caissier, on s'assure que le statut est mis à jour
            # mais généralement pour le BSC la validation DG vient approuver le décaissement.
        else:
            mouvement.statut = "REJETEE"

        self.db.flush()

        # Régénérer le PDF
        pdf_url = self.generer_pdf_mouvement(mouvement)
        mouvement.piece_jointe_url = pdf_url
        if mouvement.piece_justificative:
            mouvement.piece_justificative.url_fichier = pdf_url

        self.db.commit()
        return mouvement

    def generer_pdf_mouvement(self, mouvement: MouvementCaisse) -> str:
        """Génère le PDF du bon de caisse et retourne son URL relative."""
        caissier = mouvement.validateur.nom_complet if mouvement.validateur else ""
        
        # Trouver la signature DG si elle existe
        dg_nom = ""
        if mouvement.piece_justificative and mouvement.piece_justificative.signature_dg:
            dg_user = self.db.query(Utilisateur).filter(Utilisateur.id == mouvement.piece_justificative.id_mouvement).first() # ou DG par défaut
            dg_nom = dg_user.nom_complet if dg_user else "Direction Générale"

        if mouvement.type_mouvement == "ENTREE":
            pdf_bytes = generer_bec_pdf(mouvement, caissier, dg_nom)
        else:
            pdf_bytes = generer_bsc_pdf(mouvement, caissier, dg_nom)

        upload_dir = os.path.join(os.getcwd(), "static", "bons_caisse")
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{mouvement.numero_piece}_{int(datetime.utcnow().timestamp())}.pdf"
        filepath = os.path.join(upload_dir, filename)

        with open(filepath, "wb") as f:
            f.write(pdf_bytes)

        return f"/static/bons_caisse/{filename}"

    def lister_mouvements(self, filter_type: Optional[str] = None, page: int = 1, limit: int = 10) -> dict:
        query = self.db.query(MouvementCaisse)
        if filter_type:
            query = query.filter(MouvementCaisse.type_mouvement == filter_type)

        total = query.count()
        pages = (total + limit - 1) // limit
        items = query.order_by(MouvementCaisse.date_mouvement.desc()).offset((page - 1) * limit).limit(limit).all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "pages": pages
        }

    def obtenir_mouvement(self, id_mouvement: int) -> Optional[MouvementCaisse]:
        return self.db.query(MouvementCaisse).filter(MouvementCaisse.id_mouvement == id_mouvement).first()

    def get_solde_caisse(self) -> dict:
        # Récupère la caisse principale active
        caisse = self.db.query(Caisse).filter(Caisse.statut == "ACTIF").first()
        if not caisse:
            caisse = Caisse(solde_physique=0.0, solde_theorique=0.0, devise="USD", statut="ACTIF")
            self.db.add(caisse)
            self.db.commit()
            self.db.refresh(caisse)

        return {
            "solde_physique": caisse.solde_physique,
            "solde_theorique": caisse.solde_theorique,
            "devise": caisse.devise
        }
