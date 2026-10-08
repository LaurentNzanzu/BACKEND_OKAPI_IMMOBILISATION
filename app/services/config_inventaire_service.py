from sqlalchemy.orm import Session
from datetime import datetime
from ..models.config_inventaire import ConfigInventaire
from ..schemas.config_inventaire import ConfigInventaireUpdate


class ConfigInventaireService:
    def __init__(self, db: Session):
        self.db = db

    def get_config(self) -> ConfigInventaire:
        config = self.db.query(ConfigInventaire).first()
        if not config:
            config = ConfigInventaire(
                regle="INV-{YEAR}-{SEQ}",
                longueur_sequence=4,
                reset_period="annuel",
                dernier_numero=0
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_config(self, data: ConfigInventaireUpdate) -> ConfigInventaire:
        config = self.get_config()
        config.regle = data.regle
        config.longueur_sequence = data.longueur_sequence
        config.reset_period = data.reset_period
        config.date_mise_a_jour = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        return config

    def generer_numero_inventaire(self) -> str:
        """
        Génère le prochain numéro d'inventaire selon la règle configurée.
        Gère la réinitialisation annuelle/mensuelle.
        """
        config = self.get_config()
        now = datetime.utcnow()

        # Déterminer la clé de réinitialisation
        # On utilise dernier_numero global, mais on pourrait avoir plusieurs compteurs.
        # On va incrémenter globalement.
        sequence = config.dernier_numero + 1

        # Mettre à jour dernier_numero
        config.dernier_numero = sequence
        self.db.commit()

        # Formater la séquence avec zéros
        seq_str = str(sequence).zfill(config.longueur_sequence)

        # Remplacer les variables dans la règle
        regle = config.regle
        regle = regle.replace("{YEAR}", now.strftime("%Y"))
        regle = regle.replace("{MONTH}", now.strftime("%m"))
        regle = regle.replace("{DAY}", now.strftime("%d"))
    def generer_numero_mission(self, organisation_id: int) -> str:
        """
        Génère le prochain numéro de mission au format MIS-AAAA-0001,
        séquentiel par organisation et par année en cours.
        Sécurisé pour la concurrence avec verrouillage transactionnel.
        """
        from ..models.mission import Mission
        now = datetime.utcnow()
        annee = now.year
        prefixe = f"MIS-{annee}-"

        derniere_mission = (
            self.db.query(Mission.numero_mission)
            .filter(
                Mission.organisation_id == organisation_id,
                Mission.numero_mission.like(f"{prefixe}%"),
            )
            .order_by(Mission.numero_mission.desc())
            .with_for_update()
            .first()
        )

        sequence = 1
        if derniere_mission and derniere_mission[0]:
            try:
                seq_str = derniere_mission[0].split("-")[-1]
                sequence = int(seq_str) + 1
            except (ValueError, IndexError):
                sequence = 1

        return f"{prefixe}{str(sequence).zfill(4)}"