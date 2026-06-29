# backend/app/core/constants.py
"""
Fichier de configuration des constantes globales pour l'application.
Contient les seuils, facteurs de calcul et paramètres de scheduling.
"""

# ============================================================
# SEUILS DE FIABILITÉ - TÂCHE 3
# ============================================================

# Seuils pour le score de fiabilité (sur 100)
SEUIL_SCORE_CRITIQUE = 30.0  # En dessous → maintenance préventive auto (rouge)
SEUIL_SCORE_MOYEN = 60.0     # Entre 30 et 60 → surveillance (orange)
SEUIL_SCORE_BON = 100.0      # Au-dessus 60 → bon (vert)

# ============================================================
# SEUILS VNC (Valeur Nette Comptable) - TÂCHE 3
# ============================================================

# Seuils d'alerte pour la VNC (en pourcentage de la valeur d'origine)
SEUIL_VNC_CRITIQUE = 20.0    # 20% pour les biens critiques
SEUIL_VNC_STANDARD = 5.0     # 5% pour les biens standards

# ============================================================
# FACTEURS DE CALCUL - TÂCHE 3
# ============================================================

# Facteurs pour le calcul du score de fiabilité
FACTEUR_FREQUENCE_PANNES = 2.5   # Poids par panne dans le score (déduction)
POIDS_COUT_REPARATION = 1.0      # Poids du coût des réparations dans le score
FACTEUR_AGE_MAX = 20.0           # Âge maximum considéré pour le calcul

# ============================================================
# CRON SCHEDULING - TÂCHE 3
# ============================================================

# Heure de calcul du score de fiabilité (tous les jours à 02h00)
CRON_SCORE_HOUR = 2
CRON_SCORE_MINUTE = 0

# Heure de vérification des seuils VNC (tous les jours à 03h00)
CRON_VNC_HOUR = 3
CRON_VNC_MINUTE = 0

# Heure de calcul des projections d'investissement (tous les jours à 04h00)
CRON_PROJECTION_HOUR = 4
CRON_PROJECTION_MINUTE = 0

# Heure de génération du rapport OHADA (tous les jours à 05h00)
CRON_RAPPORT_HOUR = 5
CRON_RAPPORT_MINUTE = 0

# ============================================================
# PROJECTIONS D'INVESTISSEMENT - TÂCHE 3
# ============================================================

# Période de projection (N+1 à N+5)
ANNEE_PROJECTION_DEBUT = 1  # N+1
ANNEE_PROJECTION_FIN = 5    # N+5

# Taux d'obsolescence par défaut par type de bien
TAUX_OBSOLESCENCE_DEFAUT = {
    "ORDINATEUR": 30.0,   # 30% par an
    "VEHICULE": 15.0,     # 15% par an
    "MACHINE": 10.0,      # 10% par an
    "MOBILIER": 8.0,      # 8% par an
    "AUTRE": 12.0         # 12% par an
}

# ============================================================
# SEUILS DE MAINTENANCE - TÂCHE 3
# ============================================================

# Délai de planification automatique (en jours)
DELAI_PLANIFICATION_AUTO = 1  # D+1

# Seuil de retard pour les maintenances (en jours)
SEUIL_RETARD_MAINTENANCE = 7

# ============================================================
# LIMITES ET TAILLES - GÉNÉRAL
# ============================================================

# Limite de pagination par défaut
PAGINATION_LIMIT_DEFAUT = 50
PAGINATION_LIMIT_MAX = 200

# Taille maximale pour les fichiers
TAILLE_MAX_IMAGE = 5 * 1024 * 1024  # 5 Mo

# Formats de fichiers autorisés
FORMATS_IMAGE_AUTORISES = ['jpg', 'jpeg', 'png', 'gif']

# ============================================================
# MESSAGES D'ERREUR - GÉNÉRAL
# ============================================================

class Messages:
    """Messages d'erreur et de succès standardisés."""
    
    # Erreurs
    ERREUR_NOT_FOUND = "Ressource non trouvée"
    ERREUR_VALIDATION = "Erreur de validation des données"
    ERREUR_PERMISSION = "Vous n'avez pas les droits nécessaires"
    ERREUR_DUPLICATE = "Cette ressource existe déjà"
    ERREUR_CONFLIT = "Conflit de données détecté"
    
    # Succès
    SUCCES_CREATION = "Ressource créée avec succès"
    SUCCES_MODIFICATION = "Ressource modifiée avec succès"
    SUCCES_SUPPRESSION = "Ressource supprimée avec succès"
    
    # TÂCHE 3 - Spécifiques
    ALERTE_VNC_DETECTEE = "Alerte VNC détectée pour le bien {bien}"
    MAINTENANCE_AUTO_GENEREE = "Maintenance préventive générée automatiquement"
    PROJECTION_CALCULEE = "Projection d'investissement calculée pour {annee}"
    SCORE_RECALCULE = "Score de fiabilité recalculé"

# ============================================================
# STATUTS ET COULEURS - TÂCHE 3
# ============================================================

class Couleurs:
    """Codes couleurs pour l'interface utilisateur."""
    
    # Couleurs pour le score de fiabilité
    SCORE_CRITIQUE = "#FF0000"   # Rouge
    SCORE_MOYEN = "#FF8C00"      # Orange
    SCORE_BON = "#00CC00"        # Vert
    
    # Couleurs pour les alertes VNC
    ALERTE_CRITIQUE = "#FF0000"  # Rouge
    ALERTE_STANDARD = "#FFA500"  # Orange
    ALERTE_OK = "#00CC00"        # Vert
    
    # Couleurs générales
    PRIMARY = "#2B6CB0"
    SECONDARY = "#718096"
    SUCCESS = "#48BB78"
    DANGER = "#F56565"
    WARNING = "#ED8936"
    INFO = "#4299E1"

# ============================================================
# TYPES DE BIENS - GÉNÉRAL
# ============================================================

TYPES_BIENS = [
    "ORDINATEUR",
    "VEHICULE",
    "MACHINE",
    "MOBILIER",
    "EQUIPEMENT_BUREAU",
    "MATERIEL_INFORMATIQUE",
    "MATERIEL_INDUSTRIEL",
    "AUTRE"
]

# ============================================================
# PARAMÈTRES COMPTABLES - TÂCHE 1 & 2
# ============================================================

# Durée de vie par défaut par type de bien (en années)
DUREE_VIE_DEFAUT = {
    "ORDINATEUR": 3,
    "VEHICULE": 5,
    "MACHINE": 10,
    "MOBILIER": 10,
    "EQUIPEMENT_BUREAU": 5,
    "MATERIEL_INFORMATIQUE": 3,
    "MATERIEL_INDUSTRIEL": 7,
    "AUTRE": 5
}

# ============================================================
# CONFIGURATION DES RAPPORTS - TÂCHE 3
# ============================================================

class RapportConfig:
    """Configuration des rapports et exports."""
    
    # Formats d'export autorisés
    FORMATS_EXPORT = ['PDF', 'CSV', 'EXCEL']
    
    # Orientation des pages pour les rapports
    ORIENTATION_RAPPORT = "landscape"  # paysage pour le tableau OHADA
    
    # Marges pour les rapports (en mm)
    MARGE_RAPPORT = {
        "top": 20,
        "bottom": 20,
        "left": 15,
        "right": 15
    }
    
    # Nombre maximal de lignes par page dans les rapports
    LIGNES_PAR_PAGE = 30

# ============================================================
# FUSEAUX HORAIRES - GÉNÉRAL
# ============================================================

# Fuseau horaire par défaut
FUSEAU_HORAIRE_DEFAUT = "Africa/Douala"  # Heure du Cameroun

# Format de date par défaut
FORMAT_DATE_DEFAUT = "%Y-%m-%d"
FORMAT_DATETIME_DEFAUT = "%Y-%m-%d %H:%M:%S"

# ============================================================
# STATUTS DES BIENS - GÉNÉRAL
# ============================================================

STATUTS_COMPTABLES = [
    "ACTIF",
    "EN_AMORTISSEMENT",
    "EN_DEPRECIATION",
    "CEDE",
    "MIS_AU_REBUT"
]

ETATS_BIENS = [
    "NEUF",
    "BON",
    "USAGE",
    "PANNE",
    "REFORME",
    "MAINTENANCE",
    "EN_TEST"
]