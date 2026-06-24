# backend/scripts/seed_biens.py
from app.core.database import SessionLocal
from app.models.bien import Bien, EtatBien
from app.models.vehicule import Vehicule
from app.models.ordinateur import Ordinateur
from app.models.machine import Machine
from datetime import date
import uuid

db = SessionLocal()

# Vérifier s'il y a déjà des biens
if db.query(Bien).count() > 0:
    print(f"✅ Il y a déjà {db.query(Bien).count()} biens dans la base")
else:
    print("📦 Ajout de biens de test...")
    
    # Création des véhicules
    vehicule1 = Vehicule(
        qr_code=str(uuid.uuid4()),
        date_acquisition=date(2022, 1, 15),
        prix_acquisition=20000,
        etat=EtatBien.BON,
        localisation="Garage Principal",
        description="Pick-up double cabine",
        type_bien="vehicule",
        type_vehicule="Pick-up",
        marque="Toyota",
        modele="Hilux",
        immatriculation="AB-123-CD",
        poids=2100,
        dimension="5.3m x 1.8m x 1.8m",
        type_carburant="Diesel",
        consommation_carburant=8.5,
        consommation_huile=0.5,
        type_propulsion="4x4"
    )
    db.add(vehicule1)
    
    vehicule2 = Vehicule(
        qr_code=str(uuid.uuid4()),
        date_acquisition=date(2021, 6, 20),
        prix_acquisition=15000,
        etat=EtatBien.BON,
        localisation="Parking Sud",
        description="Utilitaire 9 places",
        type_bien="vehicule",
        type_vehicule="Utilitaire",
        marque="Renault",
        modele="Trafic",
        immatriculation="EF-456-GH",
        poids=1900,
        dimension="5.0m x 1.9m x 1.9m",
        type_carburant="Diesel",
        consommation_carburant=7.8,
        consommation_huile=0.4,
        type_propulsion="4x2"
    )
    db.add(vehicule2)
    
    # Création des ordinateurs
    ordinateur1 = Ordinateur(
        qr_code=str(uuid.uuid4()),
        date_acquisition=date(2023, 3, 10),
        prix_acquisition=850,
        etat=EtatBien.NEUF,
        localisation="Bureau 204",
        description="Ordinateur portable développeur",
        type_bien="ordinateur",
        marque="Dell",
        modele="Latitude 5420",
        processeur="Intel Core i7-1165G7",
        ram="16GB",
        stockage="512GB SSD",
        adresse_ip="192.168.1.100",
        utilisateur_affecte="Jean Dupont"
    )
    db.add(ordinateur1)
    
    ordinateur2 = Ordinateur(
        qr_code=str(uuid.uuid4()),
        date_acquisition=date(2022, 8, 5),
        prix_acquisition=7500,
        etat=EtatBien.BON,
        localisation="Bureau 105",
        description="Poste administratif",
        type_bien="ordinateur",
        marque="HP",
        modele="ProBook 450",
        processeur="Intel Core i5-1135G7",
        ram="8GB",
        stockage="256GB SSD",
        adresse_ip="192.168.1.101",
        utilisateur_affecte="Marie Martin"
    )
    db.add(ordinateur2)
    
    # Création des machines
    machine1 = Machine(
        qr_code=str(uuid.uuid4()),
        date_acquisition=date(2020, 11, 12),
        prix_acquisition=125000,
        etat=EtatBien.USAGE,
        localisation="Atelier A",
        description="Machine CNC 5 axes",
        type_bien="machine",
        numero_serie="MC-SIE-001",
        fabricant="Siemens",
        modele="CNC-5000",
        puissance=15.5,
        type_alimentation="Electrique",
        tension_normal="380V",
        service_affecte="Production",
        responsable="Pierre Richard",
        consommation_elec=12.5,
        frequence_maintenance="Hebdomadaire"
    )
    db.add(machine1)
    
    machine2 = Machine(
        qr_code=str(uuid.uuid4()),
        date_acquisition=date(2023, 1, 25),
        prix_acquisition=25000,
        etat=EtatBien.NEUF,
        localisation="Atelier B",
        description="Perceuse industrielle",
        type_bien="machine",
        numero_serie="MC-BOS-002",
        fabricant="Bosch",
        modele="GWS-1000",
        puissance=2.2,
        type_alimentation="Electrique",
        tension_normal="220V",
        service_affecte="Maintenance",
        responsable="Luc Bernard",
        consommation_elec=2.0,
        frequence_maintenance="Quotidienne"
    )
    db.add(machine2)
    
    db.commit()
    print(f"✅ 6 biens ajoutés avec succès !")

# Afficher le résultat
print(f"\n📊 Total des biens dans la base: {db.query(Bien).count()}")

db.close()