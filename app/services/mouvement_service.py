from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List, Dict
from datetime import datetime

# ✅ Imports des modèles - CORRECTION PRINCIPALE
from ..models.mouvement_bien import MouvementBien, TypeMouvementEnum
from ..models.bien import Bien, EtatBien  # ✅ CORRECTION: EtatBien (pas EtatBienEnum)
from ..models.utilisateur import Utilisateur

# ✅ Imports des schemas
from ..schemas.mouvement import MouvementCreate, MouvementUpdate
from .notification_trigger_service import NotificationTriggerService


class MouvementService:
    """
    Service métier pour gérer les mouvements de biens :
    - TRANSFERT, SORTIE, CESSION, AFFECTATION, RETOUR
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # ═══ MODIF 5.22 — Injection organisation_id + suppression appel déprécié ═══
    def creer_mouvement(self, data: MouvementCreate, id_utilisateur: int, organisation_id: Optional[int] = None) -> MouvementBien:
        """
        Crée un nouveau mouvement avec validation des règles métier.
        
        Règle 1: Blocage d'état - Un bien EN_PANNE ou EN_MAINTENANCE ne peut pas être cédé/sorti
        Règle 2: Changement d'état auto - CESSION/SORTIE → REFORME, RETOUR → BON
        Règle 3: Traçabilité - id_utilisateur vient du token, pas du frontend

        ═══ 5.22 ═══ : injection de organisation_id (depuis le Bien) + suppression
        de l'appel déprécié à comptabilite_service.enregistrer_cession()
        """
        # 1. Vérifier que le bien existe
        bien = self.db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
        if not bien:
            raise ValueError(f"Bien {data.id_bien} non trouvé")
        
        # ═══ 5.22 — Résolution org_id depuis le bien ═══
        org_id = organisation_id if organisation_id is not None else getattr(bien, "organisation_id", None)
        # ═══ FIN 5.22 ═══
        
        # 2. Règle 1: Blocage d'état pour CESSION/SORTIE
        if data.type_mouvement in [TypeMouvementEnum.CESSION, TypeMouvementEnum.SORTIE]:
            if bien.etat in [EtatBien.PANNE, EtatBien.MAINTENANCE]:
                raise ValueError(
                    f"Impossible de {data.type_mouvement.value.lower()} un bien en état {bien.etat.value}. "
                    f"Veuillez d'abord résoudre la panne ou terminer la maintenance."
                )

        if data.type_mouvement == TypeMouvementEnum.CESSION and not data.prix_vente:
            raise ValueError("Le prix de vente est obligatoire pour une cession")
        
        
        # 3. Créer le mouvement avec id_utilisateur sécurisé (règle 3)
        mouvement = MouvementBien(
            id_bien=data.id_bien,
            id_utilisateur=id_utilisateur,  # ✅ Vient du token, pas du frontend
            type_mouvement=data.type_mouvement,
            date_mouvement=data.date_mouvement or datetime.utcnow(),
            localisation_source=data.localisation_source,
            localisation_destination=data.localisation_destination,
            responsable_sortie=data.responsable_sortie,
            raison=data.raison,
            piece_justificative=data.piece_justificative,
            organisation_id=org_id,   # ═══ 5.22 — AJOUT ═══
        )
        
        self.db.add(mouvement)
        self.db.flush()  # Pour avoir l'ID avant commit
        
        # 4. Règle 2: Changement d'état automatique du bien
        if data.type_mouvement in [TypeMouvementEnum.CESSION, TypeMouvementEnum.SORTIE]:
            # ✅ CORRECTION: Utiliser EtatBien.REFORME
            bien.etat = EtatBien.REFORME
            bien.date_sortie = datetime.utcnow()  # Si ce champ existe dans votre modèle Bien
        elif data.type_mouvement == TypeMouvementEnum.RETOUR:
            # ✅ CORRECTION: Utiliser EtatBien.BON
            bien.etat = EtatBien.BON
        
        self.db.commit()
        self.db.refresh(mouvement)

        # ═══ 5.22 — SUPPRESSION de l'appel déprécié à enregistrer_cession() ═══
        # Ancienne logique :
        #     compt_service = ComptabiliteService(self.db, cree_par_id=data.id_utilisateur)
        #     cession_data = CessionCreate(...)
        #     compt_service.enregistrer_cession(cession_data)
        #
        # Raison de la suppression : méthode dépréciée qui lève RuntimeError.
        # Le workflow de cession est maintenant géré par ValidationService.valider_cession().
        # ═══ FIN 5.22 ═══

        # Notifications pour CESSION/SORTIE
        if data.type_mouvement in [TypeMouvementEnum.CESSION, TypeMouvementEnum.SORTIE]:
            trigger_service = NotificationTriggerService(self.db)
            trigger_service.notifier_mouvement(mouvement)
        
        return mouvement
    # ═══ FIN MODIF 5.22 ═══
    
    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_mouvements_by_bien(self, id_bien: int, skip: int = 0, limit: int = 100, organisation_id: Optional[int] = None) -> List[MouvementBien]:
        """Récupère l'historique complet des mouvements d'un bien"""
        query = self.db.query(MouvementBien).filter(
            MouvementBien.id_bien == id_bien
        )
        if organisation_id is not None:
            query = query.filter(MouvementBien.organisation_id == organisation_id)
        return query.order_by(
            desc(MouvementBien.date_mouvement)
        ).offset(skip).limit(limit).all()
    
    def get_all_mouvements(self, 
                          skip: int = 0, 
                          limit: int = 100,
                          type_mouvement: Optional[str] = None,
                          date_debut: Optional[datetime] = None,
                          date_fin: Optional[datetime] = None,
                          id_bien: Optional[int] = None,
                          organisation_id: Optional[int] = None) -> List[MouvementBien]:
        """Liste tous les mouvements avec filtres optionnels"""
        query = self.db.query(MouvementBien)
        
        if organisation_id is not None:
            query = query.filter(MouvementBien.organisation_id == organisation_id)
        
        if type_mouvement:
            query = query.filter(MouvementBien.type_mouvement == type_mouvement)
        if date_debut:
            query = query.filter(MouvementBien.date_mouvement >= date_debut)
        if date_fin:
            query = query.filter(MouvementBien.date_mouvement <= date_fin)
        if id_bien:
            query = query.filter(MouvementBien.id_bien == id_bien)
        
        return query.order_by(
            desc(MouvementBien.date_mouvement)
        ).offset(skip).limit(limit).all()
    
    def get_mouvement(self, id_mouvement: int, organisation_id: Optional[int] = None) -> Optional[MouvementBien]:
        """Récupère un mouvement par son ID"""
        query = self.db.query(MouvementBien).filter(
            MouvementBien.id_mouvement == id_mouvement
        )
        if organisation_id is not None:
            query = query.filter(MouvementBien.organisation_id == organisation_id)
        return query.first()
    
    def update_mouvement(self, id_mouvement: int, data: MouvementUpdate, organisation_id: Optional[int] = None) -> Optional[MouvementBien]:
        """Met à jour un mouvement (seuls certains champs sont modifiables)"""
        mouvement = self.get_mouvement(id_mouvement, organisation_id=organisation_id)
        if not mouvement:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(mouvement, field):
                setattr(mouvement, field, value)
        
        self.db.commit()
        self.db.refresh(mouvement)
        return mouvement
    
    def get_statistiques_mouvements(self, annee: Optional[int] = None, organisation_id: Optional[int] = None) -> Dict:
        """Statistiques agrégées des mouvements"""
        query = self.db.query(MouvementBien)
        if organisation_id is not None:
            query = query.filter(MouvementBien.organisation_id == organisation_id)
        if annee:
            query = query.filter(MouvementBien.date_mouvement.year == annee)
        
        return {
            "total": query.count(),
            "par_type": {
                t.value: query.filter(MouvementBien.type_mouvement == t).count()
                for t in TypeMouvementEnum
            },
            "cessions_annee": query.filter(
                MouvementBien.type_mouvement == TypeMouvementEnum.CESSION
            ).count() if annee else None
        }
    # ═══ FIN MODIF 5.22 ═══