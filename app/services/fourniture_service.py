from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import datetime
import logging

from ..models.piece_rechange import PieceRechange
from ..models.fourniture_piece import FourniturePiece, StatutFourniture
from ..models.besoin import Besoin, StatutBesoin
from ..models.ligne_besoin import LigneBesoin
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..models.notification import TypeNotificationEnum
from .notification_service import NotificationService
from .piece_service import PieceService
from .audit_service import AuditService
from ..models.bien import Bien

logger = logging.getLogger(__name__)


class FournitureService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.piece_service = PieceService(db)
        self.audit_service = AuditService(db)

    # ═══ 5.22 — Helpers multi-tenant ═══
    def _get_organisation_id_besoin(self, id_besoin: Optional[int]) -> Optional[int]:
        if not id_besoin:
            return None
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == id_besoin).first()
        if not besoin:
            return None
        org = getattr(besoin, "organisation_id", None)
        if org is not None:
            return org
        # Fallback via Panne → Bien
        from ..models.panne import Panne
        if besoin.id_panne:
            panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
            if panne and panne.id_bien:
                bien = self.db.query(Bien).filter(Bien.id_bien == panne.id_bien).first()
                return getattr(bien, "organisation_id", None) if bien else None
        return None

    def _check_acces_fourniture(self, fourniture: FourniturePiece, organisation_id: Optional[int]) -> None:
        if organisation_id is None or not fourniture:
            return
        org = getattr(fourniture, "organisation_id", None)
        if org is None:
            org = self._get_organisation_id_besoin(fourniture.id_besoin)
        if org is None:
            raise ValueError(
                f"Accès refusé : fourniture #{fourniture.id_fourniture} sans organisation."
            )
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : fourniture #{fourniture.id_fourniture} appartient à une autre organisation."
            )

    def _check_acces_besoin(self, id_besoin: int, organisation_id: Optional[int]) -> None:
        if organisation_id is None:
            return
        org = self._get_organisation_id_besoin(id_besoin)
        if org is None:
            raise ValueError(
                f"Accès refusé : besoin #{id_besoin} sans organisation."
            )
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : besoin #{id_besoin} appartient à une autre organisation."
            )
    # ═══ FIN 5.22 ═══

    # ═══ MODIF 5.22 — Vérif accès + injection organisation_id ═══
    def creer_demandes_fourniture(self, besoin_id: int, commit: bool = True, organisation_id: Optional[int] = None) -> List[FourniturePiece]:
        self._check_acces_besoin(besoin_id, organisation_id)

        besoin = (
            self.db.query(Besoin)
            .options(joinedload(Besoin.lignes).joinedload(LigneBesoin.piece))
            .filter(Besoin.id_besoin == besoin_id)
            .first()
        )
        if not besoin:
            raise ValueError("Besoin non trouvé")
        if besoin.statut not in (StatutBesoin.APPROUVEE, StatutBesoin.ATTENTE_STOCK):
            raise ValueError(
                f"Le besoin doit être APPROUVEE ou ATTENTE_STOCK (statut actuel: {besoin.statut.value})"
            )

        org_id = getattr(besoin, "organisation_id", None)

        creees = []
        for ligne in besoin.lignes:
            existante = (
                self.db.query(FourniturePiece)
                .filter(
                    FourniturePiece.id_besoin == besoin_id,
                    FourniturePiece.id_piece == ligne.id_piece,
                    FourniturePiece.statut == StatutFourniture.EN_ATTENTE,
                )
                .first()
            )
            if existante:
                continue

            fourniture = FourniturePiece(
                id_besoin=besoin_id,
                id_piece=ligne.id_piece,
                quantite_demandee=ligne.quantite,
                statut=StatutFourniture.EN_ATTENTE,
                date_creation=datetime.utcnow(),
                organisation_id=org_id,   # ═══ 5.22 ═══
            )
            self.db.add(fourniture)
            creees.append(fourniture)

        if commit:
            self.db.commit()
            for f in creees:
                self.db.refresh(f)
        else:
            self.db.flush()
        return creees

    def valider_fourniture(
        self,
        id_fourniture: int,
        quantite_fournie: int,
        id_magasinier: int,
        commentaire: str = None,
        user_id_audit: int = None,
        organisation_id: Optional[int] = None,
    ) -> FourniturePiece:
        fourniture = (
            self.db.query(FourniturePiece)
            .filter(FourniturePiece.id_fourniture == id_fourniture)
            .with_for_update()
            .first()
        )
        
        if not fourniture:
            raise ValueError("Demande de fourniture non trouvée")

        self._check_acces_fourniture(fourniture, organisation_id)

        if fourniture.statut != StatutFourniture.EN_ATTENTE:
            raise ValueError(f"La fourniture n'est plus modifiable (statut: {fourniture.statut.value})")
        if quantite_fournie <= 0 or quantite_fournie > fourniture.quantite_demandee:
            raise ValueError(
                f"Quantité invalide : doit être entre 1 et {fourniture.quantite_demandee}"
            )

        piece = self.db.query(PieceRechange).filter(PieceRechange.id_piece == fourniture.id_piece).first()
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == fourniture.id_besoin).first()
        
        if not piece:
            raise ValueError("Pièce associée non trouvée")
        
        if piece.stock_actuel < quantite_fournie:
            raise ValueError(
                f"Stock insuffisant : disponible {piece.stock_actuel}, demandé {quantite_fournie}"
            )

        org_id = getattr(fourniture, "organisation_id", None) or self._get_organisation_id_besoin(fourniture.id_besoin)

        ancien_stock = piece.stock_actuel
        self._decrementer_stock_piece(fourniture.id_piece, quantite_fournie, organisation_id=organisation_id)

        fourniture.quantite_fournie = quantite_fournie
        fourniture.date_fourniture = datetime.utcnow()
        fourniture.id_magasinier = id_magasinier
        fourniture.commentaire = commentaire
        fourniture.date_modification = datetime.utcnow()
        if getattr(fourniture, "organisation_id", None) is None:
            fourniture.organisation_id = org_id   # ═══ 5.22 ═══

        if quantite_fournie == fourniture.quantite_demandee:
            fourniture.statut = StatutFourniture.FOURNIE
        else:
            fourniture.statut = StatutFourniture.PARTIELLE
            reste = fourniture.quantite_demandee - quantite_fournie
            relance = FourniturePiece(
                id_besoin=fourniture.id_besoin,
                id_piece=fourniture.id_piece,
                quantite_demandee=reste,
                statut=StatutFourniture.EN_ATTENTE,
                commentaire=f"Relance suite fourniture partielle #{fourniture.id_fourniture}",
                date_creation=datetime.utcnow(),
                organisation_id=org_id,   # ═══ 5.22 ═══
            )
            self.db.add(relance)
            self.notification_service.envoyer_notification(
                ids_destinataires=id_magasinier,
                type_notif=TypeNotificationEnum.FOURNITURE_EN_ATTENTE,
                titre=f"📦 Relance fourniture partielle - Besoin {besoin.numero_demande if besoin else 'N/A'}",
                contenu=f"Il reste {reste} unité(s) de {piece.designation} à fournir.",
                lien="/fournitures/en-attente",
            )

        if user_id_audit:
            self.audit_service.log_update(
                user_id=user_id_audit,
                table_name="fournitures_pieces",
                record_id=fourniture.id_fourniture,
                old_values={"statut": StatutFourniture.EN_ATTENTE.value, "stock": ancien_stock},
                new_values={
                    "statut": fourniture.statut.value,
                    "quantite_fournie": quantite_fournie,
                    "stock": piece.stock_actuel,
                },
            )

        self._notifier_si_besoin_complet(fourniture.id_besoin)

        self.db.commit()
        self.db.refresh(fourniture)
        return fourniture

    def refuser_fourniture(
        self,
        id_fourniture: int,
        id_magasinier: int,
        commentaire: str,
        user_id_audit: int = None,
        organisation_id: Optional[int] = None,
    ) -> FourniturePiece:
        fourniture = (
            self.db.query(FourniturePiece)
            .options(joinedload(FourniturePiece.besoin))
            .filter(FourniturePiece.id_fourniture == id_fourniture)
            .first()
        )
        if not fourniture:
            raise ValueError("Demande de fourniture non trouvée")

        self._check_acces_fourniture(fourniture, organisation_id)

        if fourniture.statut != StatutFourniture.EN_ATTENTE:
            raise ValueError(f"La fourniture n'est plus modifiable (statut: {fourniture.statut.value})")

        fourniture.statut = StatutFourniture.REFUSEE
        fourniture.id_magasinier = id_magasinier
        fourniture.commentaire = commentaire
        fourniture.date_modification = datetime.utcnow()

        besoin = fourniture.besoin
        if besoin:
            besoin.statut = StatutBesoin.ATTENTE_STOCK

        if user_id_audit:
            self.audit_service.log_update(
                user_id=user_id_audit,
                table_name="fournitures_pieces",
                record_id=fourniture.id_fourniture,
                old_values={"statut": StatutFourniture.EN_ATTENTE.value},
                new_values={"statut": StatutFourniture.REFUSEE.value, "besoin": StatutBesoin.ATTENTE_STOCK.value},
            )

        self.db.commit()
        self.db.refresh(fourniture)
        return fourniture

    def annuler_fournitures_besoin(self, besoin_id: int, organisation_id: Optional[int] = None) -> int:
        self._check_acces_besoin(besoin_id, organisation_id)
        fournitures = (
            self.db.query(FourniturePiece)
            .filter(
                FourniturePiece.id_besoin == besoin_id,
                FourniturePiece.statut == StatutFourniture.EN_ATTENTE,
            )
            .all()
        )
        for f in fournitures:
            f.statut = StatutFourniture.ANNULEE
            f.date_modification = datetime.utcnow()
        return len(fournitures)
    # ═══ FIN MODIF 5.22 ═══

    # ═══ MODIF 5.22 — Notification filtrée par ONG ═══
    def _decrementer_stock_piece(self, id_piece: int, quantite: int, organisation_id: Optional[int] = None) -> int:
        nouveau_stock = self.piece_service.decrement_stock(id_piece, quantite)
        piece = self.piece_service.get_piece(id_piece)

        if piece and piece.est_en_stock_insuffisant():
            gestionnaire_query = (
                self.db.query(Utilisateur)
                .join(Role)
                .filter(Role.nom.in_(["GESTIONNAIRE", "ADMIN"]))
            )
            if organisation_id is not None:
                gestionnaire_query = gestionnaire_query.filter(Utilisateur.organisation_id == organisation_id)

            gestionnaires = gestionnaire_query.all()
            if gestionnaires:
                self.notification_service.envoyer_notification(
                    ids_destinataires=[g.id for g in gestionnaires],
                    type_notif=TypeNotificationEnum.ALERTE_STOCK,
                    titre=f"⚠️ Stock bas - {piece.designation}",
                    contenu=(
                        f"Le stock de {piece.designation} est tombé à {nouveau_stock} "
                        f"(minimum: {piece.stock_minimum})."
                    ),
                    lien=f"/pieces/catalogue?highlight={piece.id_piece}",
                )
        return nouveau_stock
    # ═══ FIN MODIF 5.22 ═══

    def _notifier_si_besoin_complet(self, besoin_id: int) -> None:
        en_cours = (
            self.db.query(FourniturePiece)
            .filter(
                FourniturePiece.id_besoin == besoin_id,
                FourniturePiece.statut.in_([
                    StatutFourniture.EN_ATTENTE,
                    StatutFourniture.PARTIELLE,
                ]),
            )
            .count()
        )
        if en_cours > 0:
            return

        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            return

        panne = besoin.panne
        if panne and panne.id_technicien:
            self.notification_service.envoyer_notification(
                ids_destinataires=panne.id_technicien,
                type_notif=TypeNotificationEnum.FOURNITURE_VALIDEE,
                titre=f"✅ Pièces disponibles - Besoin {besoin.numero_demande}",
                contenu=(
                    f"Les pièces du besoin {besoin.numero_demande} sont disponibles. "
                    "Vous pouvez démarrer la maintenance."
                ),
                lien=f"/pannes/{besoin.id_panne}",
            )

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_fournitures_en_attente(self, id_magasinier: int = None, organisation_id: Optional[int] = None) -> List[FourniturePiece]:
        query = (
            self.db.query(FourniturePiece)
            .options(
                joinedload(FourniturePiece.besoin),
                joinedload(FourniturePiece.piece),
            )
            .filter(FourniturePiece.statut == StatutFourniture.EN_ATTENTE)
        )
        if organisation_id is not None:
            query = query.filter(FourniturePiece.organisation_id == organisation_id)
        if id_magasinier:
            query = query.filter(
                (FourniturePiece.id_magasinier == id_magasinier)
                | (FourniturePiece.id_magasinier.is_(None))
            )
        return query.order_by(FourniturePiece.date_creation.asc()).all()

    def get_fournitures_by_besoin(self, besoin_id: int, organisation_id: Optional[int] = None) -> List[FourniturePiece]:
        self._check_acces_besoin(besoin_id, organisation_id)
        return (
            self.db.query(FourniturePiece)
            .options(joinedload(FourniturePiece.piece))
            .filter(FourniturePiece.id_besoin == besoin_id)
            .order_by(FourniturePiece.date_creation.asc())
            .all()
        )

    def get_statistiques(self, organisation_id: Optional[int] = None) -> dict:
        base_query = self.db.query(FourniturePiece)
        if organisation_id is not None:
            base_query = base_query.filter(FourniturePiece.organisation_id == organisation_id)

        total = base_query.count()
        stats = {}
        for statut in StatutFourniture:
            q = base_query.filter(FourniturePiece.statut == statut)
            stats[statut.value.lower()] = q.count()
        terminees = stats.get("fournie", 0) + stats.get("partielle", 0)
        taux = round((terminees / total * 100) if total > 0 else 0, 2)
        return {
            "total": total,
            "en_attente": stats.get("en_attente", 0),
            "fournies": stats.get("fournie", 0),
            "partielles": stats.get("partielle", 0),
            "refusees": stats.get("refusee", 0),
            "annulees": stats.get("annulee", 0),
            "taux_completion": taux,
        }
    # ═══ FIN MODIF 5.22 ═══