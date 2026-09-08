# backend/app/services/bien_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import String, func, or_
from typing import List, Optional, Dict, Any
from decimal import Decimal
import uuid
from datetime import datetime
from fastapi import HTTPException
import json
import logging

from ..models.bien import Bien, EtatBien
from ..models.type_bien import TypeBien
from ..models.composant import Composant
from ..models.localisation import Localisation
from ..models.panne import Panne
from ..models.vehicule import Vehicule
from ..models.machine import Machine
from ..models.ordinateur import Ordinateur
from ..models.maintenance import Maintenance
from ..schemas.bien import BienCreate, BienUpdate
from .qr_code_service import QRCodeService
from .config_inventaire_service import ConfigInventaireService



logger = logging.getLogger(__name__)


class BienService:
    def __init__(self, db: Session):
        self.db = db

    # ============================================================
    # MÉTHODES PRIVÉES POUR LES TYPES DYNAMIQUES
    # ============================================================

    def _get_type_bien(self, id_type_bien: int) -> Optional[TypeBien]:
        """Récupère un type de bien par son ID."""
        return self.db.query(TypeBien).filter(
            TypeBien.id == id_type_bien,
            TypeBien.est_actif == True
        ).first()

    def _get_type_bien_by_code(self, code: str) -> Optional[TypeBien]:
        """Récupère un type de bien par son code."""
        return self.db.query(TypeBien).filter(
            TypeBien.code == code,
            TypeBien.est_actif == True
        ).first()

    def _generate_qr_code_dynamique(self, type_bien: TypeBien) -> str:
        """
        Génère un QR code avec le préfixe du type de bien.
        Si le type n'a pas de code, utilise "BIEN" comme préfixe.
        """
        prefix = type_bien.code if type_bien and type_bien.code else "BIEN"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"{prefix}-{timestamp}-{unique_id}"

    def _validate_attributs_by_type(self, id_type_bien: int, attributs: Dict[str, Any]) -> bool:
        """
        Valide que les attributs obligatoires définis dans le type sont présents.
        """
        type_bien = self._get_type_bien(id_type_bien)
        if not type_bien:
            raise HTTPException(status_code=400, detail="Type de bien invalide ou inactif")

        champs_specifiques = type_bien.champs_specifiques or []
        if not champs_specifiques:
            return True

        attributs = attributs or {}

        for champ in champs_specifiques:
            if isinstance(champ, dict):
                nom = champ.get("nom")
                obligatoire = champ.get("obligatoire", False)

                if obligatoire:
                    if nom not in attributs or attributs[nom] is None or attributs[nom] == "":
                        raise HTTPException(
                            status_code=400,
                            detail=f"Le champ '{nom}' est obligatoire pour le type '{type_bien.libelle}'"
                        )

        return True

    def _convert_legacy_fields_to_attributs(self, bien_data: BienCreate, type_bien: TypeBien) -> Dict[str, Any]:
        """
        Convertit les champs legacy (type_vehicule, marque, etc.) en attributs_specifiques.
        Utilisé pour la migration progressive.
        """
        attributs = bien_data.attributs_specifiques or {}

        # Mapping des champs legacy selon le type de bien
        legacy_mapping = {
            "VEHICULE": [
                "type_vehicule", "marque", "modele", "immatriculation",
                "poids", "dimension", "type_carburant", "consommation_carburant",
                "consommation_huile", "type_propulsion"
            ],
            "MACHINE": [
                "fabricant", "modele", "puissance", "type_alimentation",
                "tension_normal", "service_affecte", "responsable",
                "consommation_elec", "frequence_maintenance", "prix_base",
                "unites_totales_prevues", "unites_consommees", "duree_fournisseur"
            ],
            "ORDINATEUR": [
                "marque", "modele", "processeur", "ram", "stockage",
                "adresse_ip", "utilisateur_affecte"
            ]
        }

        fields = legacy_mapping.get(type_bien.code, [])
        for field in fields:
            if hasattr(bien_data, field):
                value = getattr(bien_data, field)
                if value is not None:
                    attributs[field] = value

        return attributs

    def _create_bien_from_type(self, bien_data: BienCreate, type_bien: TypeBien, images: Optional[List[dict]] = None) -> Bien:
        """
        Crée un bien générique à partir des données et du type.
        """
        # Générer le numéro d'inventaire
        config_service = ConfigInventaireService(self.db)
        numero_inventaire = config_service.generer_numero_inventaire()
        
        # Validation des attributs
        attributs = self._convert_legacy_fields_to_attributs(bien_data, type_bien)
        self._validate_attributs_by_type(type_bien.id, attributs)

        # Génération du QR code dynamique
        qr_code = self._generate_qr_code_dynamique(type_bien)

        # Création du bien - TOUJOURS "bien" comme identité polymorphique !
        bien = Bien(
            qr_code=qr_code,
            date_acquisition=bien_data.date_acquisition,
            prix_acquisition=bien_data.prix_acquisition,
            etat=bien_data.etat,
            id_localisation=bien_data.id_localisation,
            date_fin_garantie=bien_data.date_fin_garantie,
            description=bien_data.libelle,
            image=None,
            # ✅ FIX : TOUJOURS "bien" - jamais le code du type !
            type_bien="bien",  # <--- CRITIQUE : NE PAS UTILISER type_bien.code
            statut_comptable="ACTIF",
            cumul_amortissement=Decimal('0'),
            cumul_depreciation=Decimal('0'),
            mode_paiement=bien_data.mode_paiement.value if bien_data.mode_paiement else "credit",
            fournisseur_id=bien_data.fournisseur_id,
            id_type_bien=type_bien.id,  # ← La référence au type via sa clé étrangère
            attributs_specifiques=attributs,
            numero_inventaire=numero_inventaire,
            images=images or []
        )

        # Gestion des composants pour les machines
        if bien_data.composants and type_bien.code == "MACHINE":
            self.db.add(bien)
            self.db.flush()
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

        return bien
    # ============================================================
    # CRUD PRINCIPAL AVEC TYPES DYNAMIQUES
    # ============================================================

    def create_bien(self, bien_data: BienCreate, images: Optional[List[dict]] = None) -> Bien:
        """
        Crée un nouveau bien avec gestion des types dynamiques.
        
        Soit on utilise id_type_bien (recommandé), soit type_bien (legacy).
        """
        # Vérifier la localisation
        self._validate_localisation(bien_data.id_localisation)

        # Déterminer le type de bien
        type_bien = None
        if bien_data.id_type_bien:
            type_bien = self._get_type_bien(bien_data.id_type_bien)
        elif bien_data.type_bien:
            # Mode legacy : trouver le type par code
            type_bien = self._get_type_bien_by_code(bien_data.type_bien.upper())

        if not type_bien:
            # Type par défaut "AUTRE"
            type_bien = self._get_type_bien_by_code("AUTRE")
            if not type_bien:
                raise HTTPException(
                    status_code=400,
                    detail="Type de bien 'AUTRE' non trouvé. Veuillez configurer les types de biens."
                )

        # Pour les machines, le prix est calculé automatiquement
        if type_bien.code == "MACHINE":
            prix_base = bien_data.prix_base or Decimal("0")
            composants = bien_data.composants or []
            total_composants = sum((c.prix_achat for c in composants), Decimal("0"))
            prix_calcule = prix_base + total_composants

            if bien_data.prix_acquisition is not None and bien_data.prix_acquisition != prix_calcule:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Le prix d'acquisition d'une machine de production est calculé automatiquement "
                        "(prix de base + somme des prix d'achat des composants)."
                    ),
                )
            bien_data.prix_acquisition = prix_calcule

        # Créer le bien
        bien = self._create_bien_from_type(bien_data, type_bien, images=images)  # <--- images passé

        self.db.add(bien)
        self.db.commit()
        self.db.refresh(bien)

        # Générer l'écriture comptable
        try:
            from .comptabilite_service import ComptabiliteService
            ComptabiliteService(self.db).generer_ecriture_acquisition(bien)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erreur lors de la génération de l'écriture d'acquisition: {str(e)}")
            raise RuntimeError(f"Impossible de générer l'écriture comptable: {str(e)}")

        return bien
    def get_bien_by_id(self, bien_id: int) -> Optional[Bien]:
        """
        Récupère un bien avec ses relations.
        """
        return (
            self.db.query(Bien)
            .options(
                joinedload(Bien.localisation_ref),
                joinedload(Bien.type_bien_ref)
            )
            .filter(Bien.id_bien == bien_id)
            .first()
        )

    def update_bien(self, bien_id: int, bien_data: BienUpdate) -> Optional[Bien]:
        """
        Met à jour un bien avec gestion des types dynamiques.
        """
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return None

        update_data = bien_data.model_dump(exclude_unset=True)

        # Si le type change, valider les attributs
        if "id_type_bien" in update_data:
            type_bien = self._get_type_bien(update_data["id_type_bien"])
            if not type_bien:
                raise HTTPException(status_code=400, detail="Type de bien invalide")

            # Mettre à jour le type
            bien.id_type_bien = type_bien.id
            bien.type_bien = type_bien.code.lower()

        # Mettre à jour les attributs spécifiques
        if "attributs_specifiques" in update_data:
            attributs = update_data["attributs_specifiques"]
            if bien.id_type_bien:
                self._validate_attributs_by_type(bien.id_type_bien, attributs)
            bien.attributs_specifiques = attributs

        # Valider la localisation
        if "id_localisation" in update_data:
            self._validate_localisation(update_data["id_localisation"])

        # Mettre à jour les champs de base
        fields_to_update = [
            "date_acquisition", "prix_acquisition", "etat", "id_localisation",
            "date_fin_garantie", "description", "image", "mode_paiement",
            "fournisseur_id", "statut_comptable"
        ]

        for field in fields_to_update:
            if field in update_data and update_data[field] is not None:
                setattr(bien, field, update_data[field])

        self.db.commit()
        self.db.refresh(bien)
        return bien

    def delete_bien(self, bien_id: int) -> bool:
        """Supprime un bien."""
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return False

        self.db.delete(bien)
        self.db.commit()
        return True

    # ============================================================
    # MÉTHODES DE RECHERCHE AVEC TYPES DYNAMIQUES
    # ============================================================

    def get_all_biens(
        self,
        skip: int = 0,
        limit: int = 100,
        type_bien: Optional[str] = None,
        etat: Optional[EtatBien] = None,
        search: Optional[str] = None,
        disponible_maintenance: bool = False,
    ) -> List[Bien]:
        """
        Récupère tous les biens avec filtres.
        """
        query = self.db.query(Bien).options(
            joinedload(Bien.localisation_ref),
            joinedload(Bien.type_bien_ref)
        )

        if type_bien:
            # Support du filtre par code ou libelle
            type_obj = self._get_type_bien_by_code(type_bien.upper())
            if type_obj:
                query = query.filter(Bien.id_type_bien == type_obj.id)
            else:
                query = query.filter(Bien.type_bien == type_bien)

        if etat:
            query = query.filter(Bien.etat == etat)

        if disponible_maintenance:
            query = query.filter(
                Bien.etat != EtatBien.MAINTENANCE,
                Bien.etat != EtatBien.REFORME
            )

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Bien.description.ilike(term),
                    Bien.qr_code.ilike(term),
                    Bien.attributs_specifiques.astext.cast(String).ilike(term)
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
        disponible_maintenance: bool = False,
    ) -> List[Bien]:
        """Récupère tous les biens (le technicien peut tout voir)."""
        return self.get_all_biens(skip, limit, type_bien, etat, search, disponible_maintenance)

    def get_biens_count(
        self,
        type_bien: Optional[str] = None,
        etat: Optional[EtatBien] = None,
        search: Optional[str] = None,
        disponible_maintenance: bool = False,
    ) -> int:
        """Compte le nombre de biens avec filtres."""
        query = self.db.query(func.count(Bien.id_bien))

        if type_bien:
            type_obj = self._get_type_bien_by_code(type_bien.upper())
            if type_obj:
                query = query.filter(Bien.id_type_bien == type_obj.id)
            else:
                query = query.filter(Bien.type_bien == type_bien)

        if etat:
            query = query.filter(Bien.etat == etat)

        if disponible_maintenance:
            query = query.filter(
                Bien.etat != EtatBien.MAINTENANCE,
                Bien.etat != EtatBien.REFORME
            )

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Bien.description.ilike(term),
                    Bien.qr_code.ilike(term),
                    Bien.attributs_specifiques.astext.cast(String).ilike(term)
                )
            )

        return query.scalar() or 0

    # ============================================================
    # MÉTHODES UTILITAIRES
    # ============================================================

    def _validate_localisation(self, id_localisation: int) -> None:
        """Vérifie que la localisation existe."""
        loc = self.db.query(Localisation).filter(
            Localisation.id_localisation == id_localisation
        ).first()
        if not loc:
            raise HTTPException(status_code=400, detail="Localisation invalide")

    def generate_and_save_qr_code(self, bien: Bien) -> str:
        """Génère et sauvegarde le QR code du bien."""
        qr_service = QRCodeService()
        qr_image = qr_service.generate_qr_code(data=bien.qr_code, bien_id=bien.id_bien)
        file_path = qr_service.generate_qr_file_path(bien.qr_code)
        with open(file_path, "wb") as f:
            f.write(qr_image)
        return str(file_path)

    def calculer_age_bien(self, bien_id: int) -> Optional[int]:
        """Calcule l'âge du bien en années."""
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return None
        return bien.calcul_age()

    def changer_etat_bien(self, bien_id: int, nouvel_etat: EtatBien, commit: bool = True) -> Optional[Bien]:
        """Change l'état d'un bien."""
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            return None

        bien.changer_etat(nouvel_etat)
        if commit:
            self.db.commit()
            self.db.refresh(bien)
        return bien

    def get_statistics(self) -> dict:
        """Récupère les statistiques des biens."""
        total = self.db.query(func.count(Bien.id_bien)).scalar()

        par_type = self.db.query(
            Bien.id_type_bien,
            func.count(Bien.id_bien),
        ).group_by(Bien.id_type_bien).all()

        # Récupérer les libellés des types
        type_stats = []
        for type_id, count in par_type:
            type_bien = self._get_type_bien(type_id)
            type_stats.append({
                "id": type_id,
                "libelle": type_bien.libelle if type_bien else "Inconnu",
                "count": count
            })

        par_etat = self.db.query(
            Bien.etat,
            func.count(Bien.id_bien),
        ).group_by(Bien.etat).all()

        return {
            "total": total,
            "par_type": type_stats,
            "par_etat": {e.value: c for e, c in par_etat},
        }

    def get_referentiel_options(self) -> dict:
        """
        Extrait les options distinctes pour alimenter les listes déroulantes du frontend.
        """
        # Récupérer les types de biens disponibles
        types_biens = self.db.query(TypeBien).filter(TypeBien.est_actif == True).all()
        types_biens_disponibles = [
            {
                "id": t.id,
                "libelle": t.libelle,
                "code": t.code,
                "compte_comptable": t.compte_comptable,
                "champs_specifiques": t.champs_specifiques
            }
            for t in types_biens
        ]

        return {
            "types_biens_disponibles": types_biens_disponibles,
            "marques_vehicules": sorted(self._get_distinct_values(Vehicule.marque)),
            "marques_ordinateurs": sorted(self._get_distinct_values(Ordinateur.marque)),
            "modeles_vehicules": sorted(self._get_distinct_values(Vehicule.modele)),
            "modeles_ordinateurs": sorted(self._get_distinct_values(Ordinateur.modele)),
            "fabricants_machines": sorted(self._get_distinct_values(Machine.fabricant)),
            "processeurs_ordinateurs": sorted(self._get_distinct_values(Ordinateur.processeur)),
        }

    def _get_distinct_values(self, column) -> List[str]:
        """Récupère les valeurs distinctes d'une colonne."""
        result = self.db.query(column).filter(column.isnot(None)).distinct().all()
        return [r[0] for r in result if r[0]]

    def get_biens_disponibles_pour_maintenance(self) -> List[Bien]:
        """Récupère les biens disponibles pour la maintenance."""
        return (
            self.db.query(Bien)
            .filter(Bien.etat != EtatBien.MAINTENANCE)
            .filter(Bien.etat != EtatBien.REFORME)
            .all()
        )

    def lier_actif_remplacement(self, bien_cede_id: int, bien_remplacement_id: int) -> Bien:
        """Lie un bien de remplacement à un bien cédé."""
        bien_cede = self.get_bien_by_id(bien_cede_id)
        if not bien_cede:
            raise ValueError("Bien cédé non trouvé")

        bien_remplacement = self.get_bien_by_id(bien_remplacement_id)
        if not bien_remplacement:
            raise ValueError("Bien de remplacement non trouvé")

        if bien_remplacement.actif_remplace:
            raise ValueError("Ce bien de remplacement est déjà lié à une autre cession")

        if bien_cede.actif_remplacement_id:
            raise ValueError("Ce bien a déjà un actif de remplacement")

        bien_cede.actif_remplacement_id = bien_remplacement_id
        self.db.commit()
        self.db.refresh(bien_cede)

        return bien_cede

    # ============================================================
    # MÉTHODES DE CESSION - TÂCHE 2 (CONSERVÉES)
    # ============================================================

    def verifier_eligibilite_cession(self, bien_id: int) -> dict:
        """Vérifie si un bien est éligible à la cession."""
        bien = self.get_bien_by_id(bien_id)
        if not bien:
            raise ValueError("Bien non trouvé")

        from ..models.amortissement import Amortissement
        from ..models.panne import StatutPanne

        amortissements = self.db.query(Amortissement).filter(
            Amortissement.id_bien == bien_id
        ).order_by(Amortissement.exercice.desc()).all()

        pannes = self.db.query(Panne).filter(
            Panne.id_bien == bien_id
        ).order_by(Panne.date_declaration.desc()).all()

        maintenances = self.db.query(Maintenance).filter(
            Maintenance.id_bien == bien_id
        ).all()

        nb_pannes_totales = len(pannes)
        nb_maintenances = len(maintenances)
        age_bien_ans = bien.calcul_age() if hasattr(bien, 'calcul_age') else 0

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
            "nb_pannes_totales": nb_pannes_totales,
            "nb_maintenances": nb_maintenances,
            "age_bien_ans": age_bien_ans,
        }

    def verifier_eligibilite_cession_optimise(self, bien: Bien) -> dict:
        """Version optimisée de la vérification d'éligibilité."""
        from ..models.panne import StatutPanne

        amortissements = bien.amortissements or []
        pannes = bien.pannes or []
        maintenances = bien.maintenances or []

        nb_pannes_totales = len(pannes)
        nb_maintenances = len(maintenances)
        age_bien_ans = bien.calcul_age() if hasattr(bien, 'calcul_age') else 0

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
            "nb_pannes_totales": nb_pannes_totales,
            "nb_maintenances": nb_maintenances,
            "age_bien_ans": age_bien_ans,
        }

    def _verifier_garantie_expiree(self, bien: Bien) -> bool:
        if not bien.date_fin_garantie:
            return True
        return bien.date_fin_garantie < datetime.utcnow().date()

    def _verifier_etat_degrade(self, bien: Bien) -> bool:
        return bien.etat in [EtatBien.USAGE, EtatBien.PANNE, EtatBien.REFORME]

    def _verifier_amortissement_termine(self, amortissements: List) -> bool:
        if not amortissements:
            return False
        amort = amortissements[0]
        return amort.valeur_nette_comptable < (amort.valeur_origine * 0.05)

    def _verifier_cycles_techniques_obligatoires(self, bien: Bien) -> bool:
        if bien.type_bien == "machine":
            if hasattr(bien, 'service_affecte'):
                if "eau" in (bien.service_affecte or "").lower():
                    return True
        return False

    def _compter_pannes_consecutives(self, pannes: List, StatutPanne) -> int:
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
        for amort in amortissements:
            if amort.montant_depreciation and amort.montant_depreciation > 0:
                return True
        return False

    def _get_bien_designation(self, bien: Bien) -> str:
        if bien.attributs_specifiques:
            marque = bien.attributs_specifiques.get('marque')
            modele = bien.attributs_specifiques.get('modele')
            if marque:
                return f"{marque} {modele or ''}".strip()

        if hasattr(bien, 'marque') and bien.marque:
            return f"{bien.marque} {getattr(bien, 'modele', '')}".strip()
        if hasattr(bien, 'fabricant') and bien.fabricant:
            return f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip()
        return f"Bien #{bien.id_bien}"