# backend/app/services/besoin_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func
from typing import Optional, List
from datetime import datetime

from ..models.besoin import Besoin, StatutBesoin
from ..models.ligne_besoin import LigneBesoin
from ..models.piece_rechange import PieceRechange
from ..models.panne import Panne, StatutPanne
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..schemas.besoin import BesoinCreate, BesoinUpdate
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum

class BesoinService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    def _generer_numero_demande(self) -> str:
        annee = datetime.utcnow().year
        count = self.db.query(Besoin).filter(Besoin.date_creation >= datetime(annee, 1, 1)).count()
        return f"DEM-{annee}-{count + 1:04d}"

    def create_besoin(self, data: BesoinCreate) -> Besoin:
        panne = self.db.query(Panne).filter(Panne.id_panne == data.id_panne).first()
        if not panne:
            raise ValueError(f"Panne {data.id_panne} non trouvée")
        
        besoin = Besoin(
            id_panne=data.id_panne,
            numero_demande=self._generer_numero_demande(),
            observations=data.observations,
            statut=StatutBesoin.BROUILLON
        )
        self.db.add(besoin)
        self.db.flush()
        
        total = 0
        for ligne_data in data.lignes:
            piece = self.db.query(PieceRechange).filter(PieceRechange.id_piece == ligne_data.id_piece).first()
            if not piece:
                raise ValueError(f"Pièce {ligne_data.id_piece} non trouvée")
            
            ligne = LigneBesoin(
                id_besoin=besoin.id_besoin,
                id_piece=ligne_data.id_piece,
                quantite=ligne_data.quantite,
                prix_unitaire=piece.prix_achat,
                prix_total=ligne_data.quantite * piece.prix_achat
            )
            self.db.add(ligne)
            total += ligne.prix_total
        
        besoin.montant_total = total
        self.db.commit()
        
        # 🆕 ENVOYER LES NOTIFICATIONS APRÈS CRÉATION
        self._envoyer_notifications_besoin_cree(besoin)
        
        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == besoin.id_besoin).first()
        
        panne.statut = StatutPanne.EN_VALIDATION
        panne.cout_total_reparation = total
        self.db.commit()

        return besoin

    def _envoyer_notifications_besoin_cree(self, besoin: Besoin):
        """Envoie une notification unique aux DG, Comptable et Caisse"""
        try:
            # Récupérer les IDs des utilisateurs par rôle
            dg_users = self.db.query(Utilisateur.id).join(Role).filter(Role.nom == "DG").all()
            comptable_users = self.db.query(Utilisateur.id).join(Role).filter(Role.nom == "COMPTABLE").all()
            caisse_users = self.db.query(Utilisateur.id).join(Role).filter(Role.nom == "CAISSE").all()
            
            ids_destinataires = [u.id for u in dg_users + comptable_users + caisse_users]
            
            titre = f"📋 Nouvelle demande de besoin - {besoin.numero_demande}"
            contenu = f"Le technicien a soumis la demande {besoin.numero_demande} d'un montant de {besoin.montant_total:,.0f} USD. Veuillez valider."
            lien = f"/validations/{besoin.id_besoin}"
            
            # Une seule notification pour tous
            self.notification_service.envoyer_notification(
                ids_destinataires=ids_destinataires,
                type_notif=TypeNotificationEnum.BESOIN_CREE,
                titre=titre,
                contenu=contenu,
                lien=lien
            )
            print(f"✅ Notification unique envoyée à {len(ids_destinataires)} utilisateur(s)")
        except Exception as e:
            print(f"❌ Erreur envoi notification: {e}")
    def get_besoin(self, id_besoin: int) -> Optional[Besoin]:
        return self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()

    def get_besoins_by_panne(self, id_panne: int) -> List[Besoin]:
        return self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_panne == id_panne).order_by(Besoin.date_creation.desc()).all()

    def get_besoins_a_valider(self, role: str) -> List[Besoin]:
        if role == "DG":
            statut_attente = StatutBesoin.BROUILLON
        elif role == "COMPTABLE":
            statut_attente = StatutBesoin.DG_VALIDE
        elif role == "CAISSE":
            statut_attente = StatutBesoin.COMPTABLE_VALIDE
        else:
            return []
        
        return self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.statut == statut_attente).all()

    def valider_besoin(self, id_besoin: int, id_validateur: int, ordre: str, decision: str, commentaire: str = None) -> Optional[Besoin]:
        besoin = self.get_besoin(id_besoin)
        if not besoin:
            return None
        
        if not besoin.peut_etre_validee(ordre):
            raise ValueError(f"Ce besoin n'est pas en attente de validation par {ordre}")
        
        from ..models.validation import Validation
        validation = Validation(
            id_besoin=id_besoin,
            id_validateur=id_validateur,
            ordre_validateur=ordre,
            decision=decision,
            commentaire=commentaire
        )
        self.db.add(validation)
        
        if decision == "REJETE":
            besoin.statut = StatutBesoin.REJETE
            panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
            if panne:
                panne.statut = StatutPanne.DIAGNOSTIQUEE
        else:
            if ordre == "CAISSE":
                besoin.statut = StatutBesoin.APPROUVEE
                panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
                if panne:
                    panne.statut = StatutPanne.EN_COURS
            else:
                besoin.passer_validation_suivante()
        
        self.db.commit()
        
        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()
        
        return besoin

    def update_besoin(self, id_besoin: int, data: BesoinUpdate) -> Optional[Besoin]:
        besoin = self.get_besoin(id_besoin)
        if not besoin:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(besoin, field):
                setattr(besoin, field, value)
        
        self.db.commit()
        
        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()
        
        return besoin

    # ✅ NOUVELLE MÉTHODE POUR LA PHASE 2
    def ajouter_ligne(self, id_besoin: int, id_piece: int, quantite: int) -> Besoin:
        """
        Ajoute une ligne à un besoin existant (ou met à jour la quantité si déjà présente).
        """
        # 1. Vérifier que le besoin existe
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            raise ValueError("Besoin non trouvé")

        # 2. Vérifier que le statut est BROUILLON
        if besoin.statut != StatutBesoin.BROUILLON:
            raise ValueError("Seuls les besoins en BROUILLON peuvent être modifiés")

        # 3. Vérifier que la pièce existe et est active
        piece = self.db.query(PieceRechange).filter(PieceRechange.id_piece == id_piece).first()
        if not piece:
            raise ValueError("Pièce non trouvée")
        if not piece.est_active:
            raise ValueError("Pièce inactive")

        # 4. Vérifier que la quantité > 0
        if quantite <= 0:
            raise ValueError("La quantité doit être supérieure à 0")

        # 5. Vérifier si la ligne existe déjà
        ligne_existante = self.db.query(LigneBesoin).filter(
            LigneBesoin.id_besoin == id_besoin,
            LigneBesoin.id_piece == id_piece
        ).first()

        if ligne_existante:
            # Mettre à jour la quantité
            ligne_existante.quantite += quantite
            ligne_existante.prix_total = ligne_existante.quantite * ligne_existante.prix_unitaire
        else:
            # Créer une nouvelle ligne
            ligne = LigneBesoin(
                id_besoin=id_besoin,
                id_piece=id_piece,
                quantite=quantite,
                prix_unitaire=piece.prix_achat,
                prix_total=quantite * piece.prix_achat
            )
            self.db.add(ligne)

        # 7. Recalculer montant_total du besoin
        total = self.db.query(sa_func.sum(LigneBesoin.prix_total)).filter(LigneBesoin.id_besoin == id_besoin).scalar() or 0
        besoin.montant_total = total

        self.db.commit()
        
        # Recharger le besoin avec ses lignes pour la réponse
        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()
        
        return besoin