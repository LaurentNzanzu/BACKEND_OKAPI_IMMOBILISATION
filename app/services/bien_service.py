# backend/app/services/bien_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import List, Optional
from decimal import Decimal
import uuid
from datetime import datetime
from fastapi import HTTPException

from ..models.bien import Bien, EtatBien
from ..models.composant import Composant
from ..models.localisation import Localisation
from ..models.panne import Panne
from ..models.vehicule import Vehicule
from ..models.machine import Machine
from ..models.ordinateur import Ordinateur
from ..schemas.bien import BienCreate, BienUpdate
from .qr_code_service import QRCodeService
import logging

logger = logging.getLogger(__name__)

PREFIX_MAPPING = {
    "vehicule": "VEH",
    "machine": "MAC",
    "ordinateur": "ORD",
}


class BienService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_qr_code(self, type_bien: str) -> str:
        prefix = PREFIX_MAPPING.get(type_bien, "BIEN")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"{prefix}-{timestamp}-{unique_id}"

    def _validate_localisation(self, id_localisation: int) -> None:
        loc = self.db.query(Localisation).filter(
            Localisation.id_localisation == id_localisation
        ).first()
        if not loc:
            raise HTTPException(status_code=400, detail="Localisation invalide")

    def _calculate_machine_price(self, bien_data: BienCreate) -> Decimal:
        prix_base = bien_data.prix_base or Decimal("0")
        composants = bien_data.composants or []
        total_composants = sum((c.prix_achat for c in composants), Decimal("0"))
        return prix_base + total_composants

    def generate_and_save_qr_code(self, bien: Bien) -> str:
        qr_service = QRCodeService()
        qr_image = qr_service.generate_qr_code(data=bien.qr_code, bien_id=bien.id_bien)
        file_path = qr_service.generate_qr_file_path(bien.qr_code)
        with open(file_path, "wb") as f:
            f.write(qr_image)
        return str(file_path)

    def create_bien(self, bien_data: BienCreate) -> Bien:
        """Crée un nouveau bien avec génération automatique du QR code."""
        self._validate_localisation(bien_data.id_localisation)

        if bien_data.type_bien == "machine":
            prix_calcule = self._calculate_machine_price(bien_data)
            if bien_data.prix_acquisition is not None and bien_data.prix_acquisition != prix_calcule:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Le prix d'acquisition d'une machine de production est calculé automatiquement "
                        "(prix de base + somme des prix d'achat des composants)."
                    ),
                )
            prix_acquisition = prix_calcule
        else:
            if bien_data.prix_acquisition is None or bien_data.prix_acquisition <= 0:
                raise HTTPException(status_code=400, detail="Un prix d'acquisition valide est requis")
            prix_acquisition = bien_data.prix_acquisition

        qr_code = self._generate_qr_code(bien_data.type_bien)

        bien_dict = {
            "qr_code": qr_code,
            "date_acquisition": bien_data.date_acquisition,
            "prix_acquisition": prix_acquisition,
            "etat": bien_data.etat,
            "id_localisation": bien_data.id_localisation,
            "date_fin_garantie": bien_data.date_fin_garantie,
            "description": bien_data.description,
            "image": bien_data.image,
            "type_bien": bien_data.type_bien,
            "statut_comptable": "ACTIF",
            "cumul_amortissement": 0,
            "cumul_depreciation": 0,
            "mode_paiement": bien_data.mode_paiement.value if bien_data.mode_paiement else "credit",
            "fournisseur_id": bien_data.fournisseur_id,
        }

        if bien_data.type_bien == "vehicule":
            bien = Vehicule(**bien_dict)
            bien.type_vehicule = bien_data.type_vehicule
            bien.marque = bien_data.marque
            bien.modele = bien_data.modele
            bien.immatriculation = bien_data.immatriculation
            bien.poids = bien_data.poids
            bien.dimension = bien_data.dimension
            bien.type_carburant = bien_data.type_carburant
            bien.consommation_carburant = bien_data.consommation_carburant
            bien.consommation_huile = bien_data.consommation_huile
            bien.type_propulsion = bien_data.type_propulsion

        elif bien_data.type_bien == "machine":
            bien = Machine(**bien_dict)
            bien.fabricant = bien_data.fabricant
            bien.modele = bien_data.modele
            bien.puissance = bien_data.puissance
            bien.type_alimentation = bien_data.type_alimentation
            bien.tension_normal = bien_data.tension_normal
            bien.service_affecte = bien_data.service_affecte
            bien.responsable = bien_data.responsable
            bien.consommation_elec = bien_data.consommation_elec
            bien.frequence_maintenance = bien_data.frequence_maintenance
            bien.prix_base = bien_data.prix_base or Decimal("0")
            bien.unites_totales_prevues = bien_data.unites_totales_prevues
            bien.unites_consommees = bien_data.unites_consommees
            bien.duree_fournisseur = bien_data.duree_fournisseur

        elif bien_data.type_bien == "ordinateur":
            bien = Ordinateur(**bien_dict)
            bien.marque = bien_data.marque
            bien.modele = bien_data.modele
            bien.processeur = bien_data.processeur
            bien.ram = bien_data.ram
            bien.stockage = bien_data.stockage
            bien.adresse_ip = bien_data.adresse_ip
            bien.utilisateur_affecte = bien_data.utilisateur_affecte
        else:
            bien = Bien(**bien_dict)

        self.db.add(bien)
        self.db.flush()

        if bien_data.type_bien == "machine" and bien_data.composants:
            for comp in bien_data.composants:
                composant = Composant(
                    id_bien=bien.id_bien,
                    designation=comp.designation or f"Composant {comp.numero_serie}",
                    numero_serie=comp.numero_serie,
                    prix_achat=comp.prix_achat,
                    valeur=float(comp.prix_achat),
                    duree_vie_ans=comp.duree_vie_ans,
                )
                self.db.add(composant)

        self.db.commit()
        self.db.refresh(bien)

        try:
            from .comptabilite_service import ComptabiliteService
            ComptabiliteService(self.db).generer_ecriture_acquisition(bien)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erreur lors de la génération de l'écriture d'acquisition: {str(e)}")
            raise RuntimeError(f"Impossible de générer l'écriture comptable: {str(e)}")

        return bien

    def get_bien_by_id(self, bien_id: int) -> Optional[Bien]:
        return (
            self.db.query(Bien)
            .options(joinedload(Bien.localisation_ref))
            .filter(Bien.id_bien == bien_id)
            .first()
        )

    def get_all_biens(
        self,
        skip: int = 0,
        limit: int = 100,
        type_bien: Optional[str] = None,
        etat: Optional[EtatBien] = None,
        search: Optional[str] = None,
    ) -> List[Bien]:
        query = self.db.query(Bien).options(joinedload(Bien.localisation_ref))

        if type_bien:
            query = query.filter(Bien.type_bien == type_bien)
        if etat:
            query = query.filter(Bien.etat == etat)
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Bien.description.ilike(term),
                    Bien.qr_code.ilike(term),
                )
            )

        return query.offset(skip).limit(limit).all()

    def get_biens_for_technicien(
            self,
            technicien_id: int,
            skip: int = 0,
            limit: int = 100,
            type_bien: Optional[str] = None,
            etat: Optional[EtatBien] = None,
            search: Optional[str] = None,
        ) -> List[Bien]:
            """Récupère tous les biens (le technicien peut tout voir)."""
            query = self.db.query(Bien).options(joinedload(Bien.localisation_ref))
            
            if type_bien:
                query = query.filter(Bien.type_bien == type_bien)
            if etat:
                query = query.filter(Bien.etat == etat)
            if search:
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        Bien.description.ilike(term),
                        Bien.qr_code.ilike(term),
                    )
                )
            return query.offset(skip).limit(limit).all()

    def get_biens_count(
        self,
        type_bien: Optional[str] = None,
        etat: Optional[EtatBien] = None,
        search: Optional[str] = None,
    ) -> int:
        query = self.db.query(func.count(Bien.id_bien))
        if type_bien:
            query = query.filter(Bien.type_bien == type_bien)
        if etat:
            query = query.filter(Bien.etat == etat)
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Bien.description.ilike(term),
                    Bien.qr_code.ilike(term),
                )
            )
        return query.scalar() or 0
    
    def update_bien(self, bien_id: int, bien_data: BienUpdate) -> Optional[Bien]:
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return None

        update_data = bien_data.model_dump(exclude_unset=True)

        if bien.type_bien == "machine" and "prix_acquisition" in update_data:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Le prix d'acquisition d'une machine de production ne peut pas être modifié manuellement."
                ),
            )

        if "id_localisation" in update_data:
            self._validate_localisation(update_data["id_localisation"])

        for field, value in update_data.items():
            setattr(bien, field, value)

        self.db.commit()
        self.db.refresh(bien)
        return bien

    def delete_bien(self, bien_id: int) -> bool:
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return False

        self.db.delete(bien)
        self.db.commit()
        return True

    def calculer_age_bien(self, bien_id: int) -> Optional[int]:
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return None
        return bien.calcul_age()

    def changer_etat_bien(self, bien_id: int, nouvel_etat: EtatBien, commit: bool = True) -> Optional[Bien]:
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return None

        bien.changer_etat(nouvel_etat)
        if commit:
            self.db.commit()
            self.db.refresh(bien)
        return bien

    def get_statistics(self) -> dict:
        total = self.db.query(func.count(Bien.id_bien)).scalar()

        par_type = self.db.query(
            Bien.type_bien,
            func.count(Bien.id_bien),
        ).group_by(Bien.type_bien).all()

        par_etat = self.db.query(
            Bien.etat,
            func.count(Bien.id_bien),
        ).group_by(Bien.etat).all()

        return {
            "total": total,
            "par_type": {t: c for t, c in par_type},
            "par_etat": {e.value: c for e, c in par_etat},
        }

    # ============================================================
    # MÉTHODES DE CESSION - TÂCHE 2
    # ============================================================
    
    def verifier_eligibilite_cession(self, bien_id: int) -> dict:
        """
        Vérifie si un bien est éligible à la cession selon les 4 règles.
        
        Règles:
        1. Garantie expirée ET excellent état → Pas de cession
        2. Garantie/Amortissement à terme ET dégradation → Cession autorisée
        3. Cycle de vie technique obligatoire → Cession obligatoire
        4. 3 pannes consécutives OU dépréciation comptable → Cession autorisée
        """
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            raise ValueError("Bien non trouvé")
        
        # Récupérer les données nécessaires
        from ..models.amortissement import Amortissement
        from ..models.panne import StatutPanne
        
        amortissements = self.db.query(Amortissement).filter(
            Amortissement.id_bien == bien_id
        ).order_by(Amortissement.exercice.desc()).all()
        
        pannes = self.db.query(Panne).filter(
            Panne.id_bien == bien_id
        ).order_by(Panne.date_declaration.desc()).all()
        
        # Calculer les critères
        garantie_expiree = self._verifier_garantie_expiree(bien)
        est_degrade = self._verifier_etat_degrade(bien)
        amortissement_termine = self._verifier_amortissement_termine(amortissements)
        cycles_techniques = self._verifier_cycles_techniques_obligatoires(bien)
        pannes_consecutives = self._compter_pannes_consecutives(pannes, StatutPanne)
        est_depecie = self._verifier_depeciation(amortissements)
        
        motifs_ineligibilite = []
        est_eligible = False
        
        # Règle 1: Garantie expirée ET excellent état → Pas de cession
        if garantie_expiree and not est_degrade:
            motifs_ineligibilite.append("Garantie expirée mais le bien est en excellent état")
        
        # Règle 2: Garantie/Amortissement à terme ET dégradation → Cession autorisée
        if (garantie_expiree or amortissement_termine) and est_degrade:
            est_eligible = True
        
        # Règle 3: Cycle de vie technique obligatoire → Cession obligatoire
        if cycles_techniques:
            est_eligible = True
        
        # Règle 4: 3 pannes consécutives OU dépréciation comptable → Cession autorisée
        if pannes_consecutives >= 3 or est_depecie:
            est_eligible = True
        
        # Si aucun critère n'est rempli, pas éligible
        if not est_eligible and not motifs_ineligibilite:
            motifs_ineligibilite.append("Aucun critère de cession rempli")
        
        # Déterminer la recommandation
        if est_eligible and cycles_techniques:
            recommandation = "Cession obligatoire pour raison sanitaire/réglementaire"
        elif est_eligible and est_degrade:
            recommandation = "Cession recommandée en raison de la dégradation du bien"
        elif est_eligible and pannes_consecutives >= 3:
            recommandation = f"Cession recommandée après {pannes_consecutives} pannes consécutives"
        elif est_eligible and est_depecie:
            recommandation = "Cession recommandée en raison de la dépréciation comptable"
        elif not est_eligible:
            recommandation = "Conserver le bien dans le parc"
        else:
            recommandation = "Éligible à la cession"
        
        # Déterminer le statut de cession
        from ..models.cession import StatutCession
        if est_eligible:
            statut_cession = StatutCession.ELIGIBLE
        else:
            statut_cession = StatutCession.EN_ATTENTE_VALIDATION
        
        return {
            "id_bien": bien.id_bien,
            "qr_code": bien.qr_code,
            "designation": self._get_bien_designation(bien),
            "est_eligible": est_eligible,
            "statut_cession": statut_cession.value,
            "criteres": {
                "garantie_expiree": garantie_expiree,
                "est_degrade": est_degrade,
                "amortissement_termine": amortissement_termine,
                "cycles_techniques_obligatoires": cycles_techniques,
                "pannes_consecutives": pannes_consecutives,
                "est_depecie": est_depecie
            },
            "motifs_ineligibilite": motifs_ineligibilite,
            "nombre_pannes_consecutives": pannes_consecutives,
            "est_depecie": est_depecie,
            "garantie_expiree": garantie_expiree,
            "amortissement_termine": amortissement_termine,
            "cycles_techniques_obligatoires": cycles_techniques,
            "recommandation": recommandation,
            "valeur_nette_comptable": bien.valeur_nette_comptable
        }

    def verifier_eligibilite_cession_optimise(self, bien: Bien) -> dict:
        """
        Version optimisée acceptant une instance de Bien dont les relations 
        (amortissements, pannes, maintenances) ont déjà été pré-chargées.
        """
        from ..models.panne import StatutPanne
        
        amortissements = bien.amortissements or []
        pannes = bien.pannes or []
        maintenances = bien.maintenances or []  # ✅ AJOUT
        
        nb_pannes_totales = len(pannes)         # ✅ AJOUT
        nb_maintenances = len(maintenances)     # ✅ AJOUT
        age_bien_ans = bien.calcul_age() if hasattr(bien, 'calcul_age') else 0  # ✅ AJOUT
        
        garantie_expiree = self._verifier_garantie_expiree(bien)
        est_degrade = self._verifier_etat_degrade(bien)
        amortissement_termine = self._verifier_amortissement_termine(amortissements)
        cycles_techniques = self._verifier_cycles_techniques_obligatoires(bien)
        pannes_consecutives = self._compter_pannes_consecutives(pannes, StatutPanne)
        est_depecie = self._verifier_depeciation(amortissements)
        
        motifs_ineligibilite = []
        est_eligible = False
        
        if garantie_expiree and not est_degrade:
            motifs_ineligibilite.append("Garantie expirée mais le bien est en excellent état")
        
        if (garantie_expiree or amortissement_termine) and est_degrade:
            est_eligible = True
        
        if cycles_techniques:
            est_eligible = True
        
        if pannes_consecutives >= 3 or est_depecie:
            est_eligible = True
        
        if not est_eligible and not motifs_ineligibilite:
            motifs_ineligibilite.append("Aucun critère de cession rempli")
        
        if est_eligible and cycles_techniques:
            recommandation = "Cession obligatoire pour raison sanitaire/réglementaire"
        elif est_eligible and est_degrade:
            recommandation = "Cession recommandée en raison de la dégradation du bien"
        elif est_eligible and pannes_consecutives >= 3:
            recommandation = f"Cession recommandée après {pannes_consecutives} pannes consécutives"
        elif est_eligible and est_depecie:
            recommandation = "Cession recommandée en raison de la dépréciation comptable"
        elif not est_eligible:
            recommandation = "Conserver le bien dans le parc"
        else:
            recommandation = "Éligible à la cession"
        
        from ..models.cession import StatutCession
        statut_cession = StatutCession.ELIGIBLE if est_eligible else StatutCession.EN_ATTENTE_VALIDATION
        
        return {
            "id_bien": bien.id_bien,
            "qr_code": bien.qr_code,
            "designation": self._get_bien_designation(bien),
            "est_eligible": est_eligible,
            "statut_cession": statut_cession.value,
            "criteres": {
                "garantie_expiree": garantie_expiree,
                "est_degrade": est_degrade,
                "amortissement_termine": amortissement_termine,
                "cycles_techniques_obligatoires": cycles_techniques,
                "pannes_consecutives": pannes_consecutives,
                "est_depecie": est_depecie
            },
            "motifs_ineligibilite": motifs_ineligibilite,
            "nombre_pannes_consecutives": pannes_consecutives,
            "est_depecie": est_depecie,
            "garantie_expiree": garantie_expiree,
            "amortissement_termine": amortissement_termine,
            "cycles_techniques_obligatoires": cycles_techniques,
            "recommandation": recommandation,
            "valeur_nette_comptable": bien.valeur_nette_comptable,
            # ✅ AJOUT DES CHAMPS MANQUANTS
            "nb_pannes_totales": nb_pannes_totales,
            "nb_maintenances": nb_maintenances,
            "age_bien_ans": age_bien_ans,
        }
    def _verifier_garantie_expiree(self, bien: Bien) -> bool:
        """Vérifie si la garantie est expirée"""
        if not bien.date_fin_garantie:
            return True
        return bien.date_fin_garantie < datetime.utcnow().date()

    def _verifier_etat_degrade(self, bien: Bien) -> bool:
        """Vérifie si le bien est en état dégradé"""
        return bien.etat in [EtatBien.USAGE, EtatBien.PANNE, EtatBien.REFORME]

    def _verifier_amortissement_termine(self, amortissements: List) -> bool:
        """Vérifie si l'amortissement est terminé"""
        if not amortissements:
            return False
        # Vérifier si la VNC est proche de 0 (moins de 5% de la valeur d'origine)
        amort = amortissements[0]
        return amort.valeur_nette_comptable < (amort.valeur_origine * 0.05)

    def _verifier_cycles_techniques_obligatoires(self, bien: Bien) -> bool:
        """
        Vérifie si le bien est soumis à des cycles techniques obligatoires.
        Exemple: Équipements de production d'eau, matériel médical, etc.
        """
        # Pour les machines de production d'eau par exemple
        if bien.type_bien == "machine":
            # Vérifier si c'est une machine de production d'eau
            if hasattr(bien, 'service_affecte'):
                if "eau" in (bien.service_affecte or "").lower():
                    return True
        return False

    def _compter_pannes_consecutives(self, pannes: List, StatutPanne) -> int:
        """Compte le nombre de pannes consécutives"""
        if not pannes:
            return 0
        
        count = 0
        for panne in pannes:
            if panne.statut in [StatutPanne.TERMINEE, StatutPanne.EN_COURS]:
                count += 1
            else:
                break
        return count

    def _verifier_depeciation(self, amortissements: List) -> bool:
        """Vérifie si le bien a fait l'objet d'une dépréciation comptable"""
        for amort in amortissements:
            if amort.montant_depreciation and amort.montant_depreciation > 0:
                return True
        return False

    def _get_bien_designation(self, bien: Bien) -> str:
        """Récupère la désignation du bien"""
        if hasattr(bien, 'marque') and bien.marque:
            return f"{bien.marque} {getattr(bien, 'modele', '')}".strip()
        if hasattr(bien, 'fabricant') and bien.fabricant:
            return f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip()
        return f"Bien #{bien.id_bien}"

    def lier_actif_remplacement(self, bien_cede_id: int, bien_remplacement_id: int) -> Bien:
        """
        Lie un bien de remplacement à un bien cédé.
        """
        bien_cede = self.get_bien_by_id(bien_cede_id)
        if not bien_cede:
            raise ValueError("Bien cédé non trouvé")
        
        bien_remplacement = self.get_bien_by_id(bien_remplacement_id)
        if not bien_remplacement:
            raise ValueError("Bien de remplacement non trouvé")
        
        # Vérifier que le bien de remplacement n'est pas déjà utilisé
        if bien_remplacement.actif_remplace:
            raise ValueError("Ce bien de remplacement est déjà lié à une autre cession")
        
        # Vérifier que le bien cédé n'a pas déjà un remplacement
        if bien_cede.actif_remplacement_id:
            raise ValueError("Ce bien a déjà un actif de remplacement")
        
        bien_cede.actif_remplacement_id = bien_remplacement_id
        
        self.db.commit()
        self.db.refresh(bien_cede)
        
        return bien_cede