# app/services/besoin_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func
from typing import Optional, List
from datetime import datetime
import random
import logging

from ..models.besoin import Besoin, StatutBesoin
from ..models.ligne_besoin import LigneBesoin
from ..models.piece_rechange import PieceRechange
from ..models.panne import Panne, StatutPanne
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..schemas.besoin import BesoinCreate, BesoinUpdate
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum

logger = logging.getLogger(__name__)


class BesoinService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    # ═══ 5.22 — Helpers multi-tenant ═══
    def _get_organisation_id_panne(self, id_panne: Optional[int]) -> Optional[int]:
        """Récupère l'organisation_id via Panne → Bien."""
        if not id_panne:
            return None
        panne = self.db.query(Panne).filter(Panne.id_panne == id_panne).first()
        if not panne or not panne.id_bien:
            return None
        from ..models.bien import Bien
        bien = self.db.query(Bien).filter(Bien.id_bien == panne.id_bien).first()
        return getattr(bien, "organisation_id", None) if bien else None

    def _get_organisation_id_besoin(self, id_besoin: Optional[int]) -> Optional[int]:
        """Récupère l'organisation_id d'un besoin (colonne directe ou via Panne)."""
        if not id_besoin:
            return None
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            return None
        org = getattr(besoin, "organisation_id", None)
        if org is not None:
            return org
        return self._get_organisation_id_panne(besoin.id_panne)

    def _check_acces_besoin(self, besoin: Besoin, organisation_id: Optional[int]) -> None:
        """Vérifie que le besoin appartient à l'organisation (None = admin plateforme)."""
        if organisation_id is None or not besoin:
            return
        org = getattr(besoin, "organisation_id", None)
        if org is None:
            org = self._get_organisation_id_panne(besoin.id_panne)
        if org is None:
            raise ValueError(
                f"Accès refusé : besoin #{besoin.id_besoin} sans organisation (donnée historique)."
            )
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : besoin #{besoin.id_besoin} appartient à une autre organisation."
            )

    def _check_acces_panne(self, id_panne: int, organisation_id: Optional[int]) -> None:
        """Vérifie que la panne appartient à l'organisation (None = admin plateforme)."""
        if organisation_id is None:
            return
        org = self._get_organisation_id_panne(id_panne)
        if org is None:
            raise ValueError(
                f"Accès refusé : panne #{id_panne} sans organisation (donnée historique)."
            )
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : panne #{id_panne} appartient à une autre organisation."
            )
    # ═══ FIN 5.22 ═══

    # ═══ MODIF 5.22 — Numéro de demande scopé par ONG ═══
    def _generer_numero_demande(self, organisation_id: Optional[int] = None) -> str:
        annee = datetime.utcnow().year
        query = self.db.query(Besoin).filter(Besoin.date_creation >= datetime(annee, 1, 1))
        if organisation_id is not None:
            query = query.filter(Besoin.organisation_id == organisation_id)
        count = query.count()
        return f"DEM-{annee}-{count + 1:04d}"
    # ═══ FIN MODIF 5.22 ═══

    def _generer_reference_hors_catalogue(self) -> str:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"99{timestamp}{random.randint(100, 999)}"

    # ═══ MODIF 5.22 — Injection organisation_id + accès ═══
    def create_besoin(self, data: BesoinCreate, organisation_id: Optional[int] = None) -> Besoin:
        logger.info(f"Création du besoin pour la panne {data.id_panne} ({len(data.lignes)} lignes)")

        panne = self.db.query(Panne).filter(Panne.id_panne == data.id_panne).first()
        if not panne:
            raise ValueError(f"Panne {data.id_panne} non trouvée")

        # Vérification d'accès
        self._check_acces_panne(panne.id_panne, organisation_id)

        if panne.statut == StatutPanne.EN_VALIDATION:
            raise ValueError(f"Impossible de créer un besoin : la panne est en cours de validation de réforme ou cession (bien irrécupérable).")
            
        from ..models.discussion_concertation import DiscussionConcertation
        concertation_active = self.db.query(DiscussionConcertation).filter(
            DiscussionConcertation.id_bien == panne.id_bien,
            DiscussionConcertation.type_validation.in_(["REBUT", "CESSION"]),
            DiscussionConcertation.est_active == True
        ).first()
        if concertation_active:
            raise ValueError(f"Impossible de créer un besoin : une concertation de type {concertation_active.type_validation.value} est en cours pour ce bien.")

        # ═══ 5.22 — Résolution organisation_id (toujours via Panne → Bien) ═══
        org_id = organisation_id if organisation_id is not None else self._get_organisation_id_panne(panne.id_panne)
        # ═══ FIN 5.22 ═══

        besoin = Besoin(
            id_panne=data.id_panne,
            numero_demande=self._generer_numero_demande(organisation_id=org_id),   # ═══ 5.22 ═══
            statut=StatutBesoin.BROUILLON,
            organisation_id=org_id,   # ═══ 5.22 ═══
        )
        self.db.add(besoin)
        self.db.flush()

        total = 0
        pieces_hors_catalogue_crees = []

        for idx, ligne_data in enumerate(data.lignes):
            if ligne_data.id_piece and ligne_data.id_piece > 0:
                piece = self.db.query(PieceRechange).filter(
                    PieceRechange.id_piece == ligne_data.id_piece
                ).first()

                if not piece:
                    raise ValueError(f"Pièce {ligne_data.id_piece} non trouvée")

                if not piece.est_active:
                    raise ValueError(f"La pièce '{piece.designation}' est inactive")

                prix_unitaire = piece.prix_achat
                id_piece_final = piece.id_piece
                est_hors_catalogue = False

            else:
                if not ligne_data.designation or not ligne_data.designation.strip():
                    raise ValueError("La désignation est obligatoire pour une pièce hors catalogue")

                if not ligne_data.prix_unitaire or ligne_data.prix_unitaire <= 0:
                    raise ValueError("Le prix unitaire est obligatoire pour une pièce hors catalogue")

                nouvelle_piece = PieceRechange(
                    numero_serie=self._generer_reference_hors_catalogue(),
                    designation=ligne_data.designation.strip(),
                    prix_achat=ligne_data.prix_unitaire,
                    prix_vente=None,
                    compatible_avec="ORDINATEUR",
                    fournisseur="Hors catalogue - créé automatiquement",
                    stock_actuel=0,
                    stock_minimum=1,
                    est_active=True,
                    date_creation=datetime.utcnow(),
                    organisation_id=org_id,   # ═══ 5.22 ═══
                )
                self.db.add(nouvelle_piece)
                self.db.flush()

                prix_unitaire = ligne_data.prix_unitaire
                id_piece_final = nouvelle_piece.id_piece
                est_hors_catalogue = True
                pieces_hors_catalogue_crees.append(nouvelle_piece.designation)

            ligne = LigneBesoin(
                id_besoin=besoin.id_besoin,
                id_piece=id_piece_final,
                quantite=ligne_data.quantite,
                prix_unitaire=prix_unitaire,
                prix_total=ligne_data.quantite * prix_unitaire,
                est_hors_catalogue=est_hors_catalogue,
                organisation_id=org_id,   # ═══ 5.22 ═══
            )
            self.db.add(ligne)
            total += ligne.prix_total

        besoin.montant_total = total
        panne.statut = StatutPanne.EN_VALIDATION
        panne.cout_total_reparation = total

        self.db.commit()

        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == besoin.id_besoin).first()

        self._envoyer_notifications_besoin_cree(besoin)

        logger.info(f"Besoin créé avec succès: {besoin.numero_demande} - Total: {total}")

        return besoin
    # ═══ FIN MODIF 5.22 ═══

    # ═══ MODIF 5.22 — Notifications filtrées par ONG ═══
    def _envoyer_notifications_besoin_cree(self, besoin: Besoin):
        try:
            org_id = getattr(besoin, "organisation_id", None)

            dg_query = self.db.query(Utilisateur.id).join(Role).filter(Role.nom == "DG")
            comptable_query = self.db.query(Utilisateur.id).join(Role).filter(Role.nom == "COMPTABLE")
            caisse_query = self.db.query(Utilisateur.id).join(Role).filter(Role.nom == "CAISSE")

            if org_id is not None:
                dg_query = dg_query.filter(Utilisateur.organisation_id == org_id)
                comptable_query = comptable_query.filter(Utilisateur.organisation_id == org_id)
                caisse_query = caisse_query.filter(Utilisateur.organisation_id == org_id)

            dg_users = dg_query.all()
            comptable_users = comptable_query.all()
            caisse_users = caisse_query.all()

            ids_destinataires = [u.id for u in dg_users + comptable_users + caisse_users]

            titre = f"📋 Nouvelle demande de besoin - {besoin.numero_demande}"
            contenu = f"Le technicien a soumis la demande {besoin.numero_demande} d'un montant de {besoin.montant_total:,.0f} USD. Veuillez valider."
            lien = f"/validations/{besoin.id_besoin}"

            self.notification_service.envoyer_notification(
                ids_destinataires=ids_destinataires,
                type_notif=TypeNotificationEnum.BESOIN_CREE,
                titre=titre,
                contenu=contenu,
                lien=lien
            )
            logger.info(f"Notification envoyée à {len(ids_destinataires)} utilisateur(s)")
        except Exception as e:
            logger.error(f"Erreur envoi notification: {e}")
    # ═══ FIN MODIF 5.22 ═══

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_besoin(self, id_besoin: int, organisation_id: Optional[int] = None) -> Optional[Besoin]:
        query = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin)
        if organisation_id is not None:
            query = query.filter(Besoin.organisation_id == organisation_id)
        return query.first()

    def get_besoins_by_panne(self, id_panne: int, organisation_id: Optional[int] = None) -> List[Besoin]:
        self._check_acces_panne(id_panne, organisation_id)
        query = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_panne == id_panne)
        if organisation_id is not None:
            query = query.filter(Besoin.organisation_id == organisation_id)
        return query.order_by(Besoin.date_creation.desc()).all()

    def get_besoins_a_valider(self, role: str, organisation_id: Optional[int] = None) -> List[Besoin]:
        if role == "DG":
            statut_attente = StatutBesoin.BROUILLON
        elif role == "COMPTABLE":
            statut_attente = StatutBesoin.DG_VALIDE
        elif role == "CAISSE":
            statut_attente = StatutBesoin.COMPTABLE_VALIDE
        else:
            return []

        query = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.statut == statut_attente)
        if organisation_id is not None:
            query = query.filter(Besoin.organisation_id == organisation_id)
        return query.all()
    # ═══ FIN MODIF 5.22 ═══

    # ═══ MODIF 5.22 — Vérif accès ═══
    def valider_besoin(self, id_besoin: int, id_validateur: int, ordre: str, decision: str, commentaire: str = None, organisation_id: Optional[int] = None) -> Optional[Besoin]:
        besoin = self.get_besoin(id_besoin, organisation_id=organisation_id)
        if not besoin:
            return None

        self._check_acces_besoin(besoin, organisation_id)

        if not besoin.peut_etre_validee(ordre):
            raise ValueError(f"Ce besoin n'est pas en attente de validation par {ordre}")

        from ..models.validation import Validation
        validation = Validation(
            id_besoin=id_besoin,
            id_validateur=id_validateur,
            ordre_validateur=ordre,
            decision=decision,
            commentaire=commentaire,
            organisation_id=getattr(besoin, "organisation_id", None),   # ═══ 5.22 ═══
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

    def update_besoin(self, id_besoin: int, data: BesoinUpdate, organisation_id: Optional[int] = None) -> Optional[Besoin]:
        besoin = self.get_besoin(id_besoin, organisation_id=organisation_id)
        if not besoin:
            return None

        self._check_acces_besoin(besoin, organisation_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(besoin, field):
                setattr(besoin, field, value)

        self.db.commit()

        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()

        return besoin

    def ajouter_ligne(self, id_besoin: int, id_piece: int, quantite: int, organisation_id: Optional[int] = None) -> Besoin:
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            raise ValueError("Besoin non trouvé")

        self._check_acces_besoin(besoin, organisation_id)

        if besoin.statut != StatutBesoin.BROUILLON:
            raise ValueError("Seuls les besoins en BROUILLON peuvent être modifiés")

        piece = self.db.query(PieceRechange).filter(PieceRechange.id_piece == id_piece).first()
        if not piece:
            raise ValueError("Pièce non trouvée")
        if not piece.est_active:
            raise ValueError("Pièce inactive")

        if quantite <= 0:
            raise ValueError("La quantité doit être supérieure à 0")

        ligne_existante = self.db.query(LigneBesoin).filter(
            LigneBesoin.id_besoin == id_besoin,
            LigneBesoin.id_piece == id_piece
        ).first()

        org_id = getattr(besoin, "organisation_id", None)

        if ligne_existante:
            ligne_existante.quantite += quantite
            ligne_existante.prix_total = ligne_existante.quantite * ligne_existante.prix_unitaire
        else:
            ligne = LigneBesoin(
                id_besoin=id_besoin,
                id_piece=id_piece,
                quantite=quantite,
                prix_unitaire=piece.prix_achat,
                prix_total=quantite * piece.prix_achat,
                est_hors_catalogue=False,
                organisation_id=org_id,   # ═══ 5.22 ═══
            )
            self.db.add(ligne)

        total = self.db.query(sa_func.sum(LigneBesoin.prix_total)).filter(
            LigneBesoin.id_besoin == id_besoin
        ).scalar() or 0
        besoin.montant_total = total

        self.db.commit()

        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()

        return besoin

    def ajouter_ligne_hors_catalogue(self, id_besoin: int, designation: str, prix_unitaire: float, quantite: int, organisation_id: Optional[int] = None) -> Besoin:
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            raise ValueError("Besoin non trouvé")

        self._check_acces_besoin(besoin, organisation_id)

        if besoin.statut != StatutBesoin.BROUILLON:
            raise ValueError("Seuls les besoins en BROUILLON peuvent être modifiés")

        org_id = getattr(besoin, "organisation_id", None)

        nouvelle_piece = PieceRechange(
            numero_serie=self._generer_reference_hors_catalogue(),
            designation=designation.strip(),
            prix_achat=prix_unitaire,
            compatible_avec="ORDINATEUR",
            fournisseur="Hors catalogue",
            stock_actuel=0,
            stock_minimum=1,
            est_active=True,
            date_creation=datetime.utcnow(),
            organisation_id=org_id,   # ═══ 5.22 ═══
        )
        self.db.add(nouvelle_piece)
        self.db.flush()

        ligne = LigneBesoin(
            id_besoin=id_besoin,
            id_piece=nouvelle_piece.id_piece,
            quantite=quantite,
            prix_unitaire=prix_unitaire,
            prix_total=quantite * prix_unitaire,
            est_hors_catalogue=True,
            organisation_id=org_id,   # ═══ 5.22 ═══
        )
        self.db.add(ligne)

        total = self.db.query(sa_func.sum(LigneBesoin.prix_total)).filter(
            LigneBesoin.id_besoin == id_besoin
        ).scalar() or 0
        besoin.montant_total = total

        self.db.commit()

        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()

        return besoin

    def supprimer_ligne(self, id_besoin: int, id_ligne: int, organisation_id: Optional[int] = None) -> Optional[Besoin]:
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            return None

        self._check_acces_besoin(besoin, organisation_id)

        if besoin.statut != StatutBesoin.BROUILLON:
            raise ValueError("Seuls les besoins en BROUILLON peuvent être modifiés")

        ligne = self.db.query(LigneBesoin).filter(
            LigneBesoin.id_ligne == id_ligne,
            LigneBesoin.id_besoin == id_besoin
        ).first()

        if not ligne:
            raise ValueError("Ligne non trouvée")

        self.db.delete(ligne)

        total = self.db.query(sa_func.sum(LigneBesoin.prix_total)).filter(
            LigneBesoin.id_besoin == id_besoin
        ).scalar() or 0
        besoin.montant_total = total

        self.db.commit()

        besoin = self.db.query(Besoin).options(
            joinedload(Besoin.lignes).joinedload(LigneBesoin.piece)
        ).filter(Besoin.id_besoin == id_besoin).first()

        return besoin
    # ═══ FIN MODIF 5.22 ═══