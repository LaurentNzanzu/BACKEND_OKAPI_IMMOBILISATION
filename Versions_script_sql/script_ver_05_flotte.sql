-- ============================================================================
-- OKAPI — Script SQL 05 — Sprint 1 : Flotte (véhicules, chauffeurs, missions,
--                          affectations, trajets)
-- Idempotent : oui (IF NOT EXISTS / DO $$ ... $$ / ON CONFLICT DO NOTHING)
-- À exécuter APRÈS script_ver_01 à script_ver_04 (organisations, projets,
-- biens, localisations, utilisateurs, mouvements_biens doivent exister).
--
-- Ordre : 0 extension | 1 tables | 2 index | 3 contraintes | 4 seed | 5 contrôles
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extension nécessaire aux contraintes anti-chevauchement (section 3)
--    (contrib PostgreSQL, incluse dans l'installation standard)
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS btree_gist;

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. TABLES  (types alignés sur les modèles SQLAlchemy de app/models/)
-- ----------------------------------------------------------------------------

-- 1.1 vehicules : extension de biens (héritage joint, PK = FK vers biens)
CREATE TABLE IF NOT EXISTS vehicules (
    id_bien                             INTEGER PRIMARY KEY,
    type_vehicule                       VARCHAR(100),
    categorie                           VARCHAR(50),
    marque                              VARCHAR(100),
    modele                              VARCHAR(100),
    immatriculation                     VARCHAR(50),
    vin                                 VARCHAR(100),
    numero_boitier_gps                  VARCHAR(100),
    poids                               DOUBLE PRECISION,
    dimension                           VARCHAR(100),
    couleur                             VARCHAR(50),
    nombre_places                       INTEGER,
    type_carburant                      VARCHAR(50),
    capacite_reservoir                  DOUBLE PRECISION,
    consommation_carburant              DOUBLE PRECISION,
    consommation_theorique              DOUBLE PRECISION,
    consommation_huile                  DOUBLE PRECISION,
    type_propulsion                     VARCHAR(50),
    kilometrage_actuel                  DOUBLE PRECISION DEFAULT 0.0,
    prochain_km_maintenance             DOUBLE PRECISION,
    date_expiration_assurance           DATE,
    date_expiration_visite_technique    DATE,
    date_expiration_permis_transport    DATE,
    CONSTRAINT fk_vehicules_bien
        FOREIGN KEY (id_bien) REFERENCES biens(id_bien) ON DELETE CASCADE
);

-- Idempotence colonnes vehicules (si la table existait déjà avec un schéma partiel)
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS categorie VARCHAR(50);
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS vin VARCHAR(100);
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS numero_boitier_gps VARCHAR(100);
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS couleur VARCHAR(50);
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS nombre_places INTEGER;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS capacite_reservoir DOUBLE PRECISION;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS consommation_theorique DOUBLE PRECISION;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS kilometrage_actuel DOUBLE PRECISION DEFAULT 0.0;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS prochain_km_maintenance DOUBLE PRECISION;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS date_expiration_assurance DATE;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS date_expiration_visite_technique DATE;
ALTER TABLE vehicules ADD COLUMN IF NOT EXISTS date_expiration_permis_transport DATE;

-- 1.2 chauffeurs
CREATE TABLE IF NOT EXISTS chauffeurs (
    id                      SERIAL PRIMARY KEY,
    organisation_id         INTEGER      NOT NULL,
    utilisateur_id          INTEGER,
    nom                     VARCHAR(100) NOT NULL,
    prenom                  VARCHAR(100) NOT NULL,
    telephone               VARCHAR(50),
    numero_permis           VARCHAR(100) NOT NULL,
    type_permis             VARCHAR(50),
    categorie_permis        VARCHAR(50),
    date_expiration_permis  DATE,
    statut                  VARCHAR(50)  DEFAULT 'DISPONIBLE',
    photo_url               VARCHAR(500),
    date_embauche           DATE,
    observations            TEXT,
    disponible              BOOLEAN DEFAULT TRUE,
    actif                   BOOLEAN DEFAULT TRUE,
    date_creation           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chauffeurs_organisation
        FOREIGN KEY (organisation_id) REFERENCES organisations(id),
    CONSTRAINT fk_chauffeurs_utilisateur
        FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE SET NULL
);

-- Idempotence colonnes chauffeurs
ALTER TABLE chauffeurs ADD COLUMN IF NOT EXISTS utilisateur_id INTEGER;
ALTER TABLE chauffeurs ADD COLUMN IF NOT EXISTS categorie_permis VARCHAR(50);
ALTER TABLE chauffeurs ADD COLUMN IF NOT EXISTS statut VARCHAR(50) DEFAULT 'DISPONIBLE';
ALTER TABLE chauffeurs ADD COLUMN IF NOT EXISTS photo_url VARCHAR(500);
ALTER TABLE chauffeurs ADD COLUMN IF NOT EXISTS date_embauche DATE;
ALTER TABLE chauffeurs ADD COLUMN IF NOT EXISTS observations TEXT;

-- 1.3 missions
CREATE TABLE IF NOT EXISTS missions (
    id                  SERIAL PRIMARY KEY,
    organisation_id     INTEGER      NOT NULL,
    projet_id           INTEGER,
    numero_mission      VARCHAR(50),
    demandeur_id        INTEGER,
    type_workflow       VARCHAR(50)  NOT NULL DEFAULT 'MISSION',
    statut              VARCHAR(50)  NOT NULL DEFAULT 'BROUILLON',
    description         TEXT,
    motif               TEXT,
    destination         VARCHAR(255),
    lieu_depart         VARCHAR(255),
    lieu_arrivee        VARCHAR(255),
    date_debut          TIMESTAMP,
    date_fin            TIMESTAMP,
    date_depart_prevue  TIMESTAMP,
    date_retour_prevue  TIMESTAMP,
    passagers           JSON DEFAULT '[]'::json,
    km_depart           DOUBLE PRECISION,
    km_arrivee          DOUBLE PRECISION,
    heure_depart_reelle TIMESTAMP,
    heure_retour_reelle TIMESTAMP,
    photo_depart_url    VARCHAR(500),
    observation         TEXT,
    devise              VARCHAR(3)   DEFAULT 'USD',
    cree_par            INTEGER,
    etape_actuelle_id   INTEGER,
    valide_par          INTEGER,
    date_validation     TIMESTAMP,
    motif_rejet         TEXT,
    date_creation       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_missions_organisation
        FOREIGN KEY (organisation_id) REFERENCES organisations(id),
    CONSTRAINT fk_missions_projet
        FOREIGN KEY (projet_id) REFERENCES projets(id),
    CONSTRAINT fk_missions_cree_par
        FOREIGN KEY (cree_par) REFERENCES utilisateurs(id),
    CONSTRAINT fk_missions_demandeur
        FOREIGN KEY (demandeur_id) REFERENCES utilisateurs(id) ON DELETE SET NULL,
    CONSTRAINT fk_missions_etape
        FOREIGN KEY (etape_actuelle_id) REFERENCES workflow_etapes(id) ON DELETE SET NULL,
    CONSTRAINT fk_missions_valide_par
        FOREIGN KEY (valide_par) REFERENCES utilisateurs(id) ON DELETE SET NULL
);

-- Idempotence colonnes missions
ALTER TABLE missions ADD COLUMN IF NOT EXISTS numero_mission VARCHAR(50);
ALTER TABLE missions ADD COLUMN IF NOT EXISTS demandeur_id INTEGER;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS motif TEXT;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS destination VARCHAR(255);
ALTER TABLE missions ADD COLUMN IF NOT EXISTS date_depart_prevue TIMESTAMP;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS date_retour_prevue TIMESTAMP;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS passagers JSON DEFAULT '[]'::json;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS km_depart DOUBLE PRECISION;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS km_arrivee DOUBLE PRECISION;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS heure_depart_reelle TIMESTAMP;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS heure_retour_reelle TIMESTAMP;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS photo_depart_url VARCHAR(500);
ALTER TABLE missions ADD COLUMN IF NOT EXISTS observation TEXT;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS devise VARCHAR(3) DEFAULT 'USD';
ALTER TABLE missions ADD COLUMN IF NOT EXISTS etape_actuelle_id INTEGER;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS valide_par INTEGER;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS date_validation TIMESTAMP;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS motif_rejet TEXT;

-- 1.4 affectations_mission (réservation véhicule / chauffeur sur une période)
CREATE TABLE IF NOT EXISTS affectations_mission (
    id                SERIAL PRIMARY KEY,
    organisation_id   INTEGER   NOT NULL,
    mission_id        INTEGER   NOT NULL,
    vehicule_id       INTEGER,
    chauffeur_id      INTEGER,
    date_debut        TIMESTAMP NOT NULL,
    date_fin          TIMESTAMP NOT NULL,
    statut            VARCHAR(50) DEFAULT 'PLANIFIEE',
    commentaire       TEXT,
    affecte_par       INTEGER,
    date_affectation  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_affectations_organisation
        FOREIGN KEY (organisation_id) REFERENCES organisations(id),
    CONSTRAINT fk_affectations_mission
        FOREIGN KEY (mission_id) REFERENCES missions(id) ON DELETE CASCADE,
    CONSTRAINT fk_affectations_vehicule
        FOREIGN KEY (vehicule_id) REFERENCES vehicules(id_bien),
    CONSTRAINT fk_affectations_chauffeur
        FOREIGN KEY (chauffeur_id) REFERENCES chauffeurs(id),
    CONSTRAINT fk_affectations_affecte_par
        FOREIGN KEY (affecte_par) REFERENCES utilisateurs(id) ON DELETE SET NULL
);

-- Idempotence colonnes affectations_mission
ALTER TABLE affectations_mission ADD COLUMN IF NOT EXISTS affecte_par INTEGER;
ALTER TABLE affectations_mission ADD COLUMN IF NOT EXISTS date_affectation TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 1.5 trajets (opérationnel ; lien FACULTATIF vers un mouvement patrimonial)
CREATE TABLE IF NOT EXISTS trajets (
    id                          SERIAL PRIMARY KEY,
    organisation_id             INTEGER NOT NULL,
    mission_id                  INTEGER,
    mouvement_bien_id           INTEGER,
    vehicule_id                 INTEGER,
    chauffeur_id                INTEGER,
    date_debut                  TIMESTAMP,
    date_fin                    TIMESTAMP,
    kilometrage_debut           DOUBLE PRECISION,
    kilometrage_fin             DOUBLE PRECISION,
    distance_km                 DOUBLE PRECISION,
    lat_depart                  DOUBLE PRECISION,
    lng_depart                  DOUBLE PRECISION,
    lat_arrivee                 DOUBLE PRECISION,
    lng_arrivee                 DOUBLE PRECISION,
    carburant_consomme_estime   DOUBLE PRECISION,
    source_donnees              VARCHAR(50) DEFAULT 'MOBILE',
    statut                      VARCHAR(50) DEFAULT 'EN_COURS',
    commentaire                 TEXT,
    CONSTRAINT fk_trajets_organisation
        FOREIGN KEY (organisation_id) REFERENCES organisations(id),
    CONSTRAINT fk_trajets_mission
        FOREIGN KEY (mission_id) REFERENCES missions(id) ON DELETE CASCADE,
    CONSTRAINT fk_trajets_mouvement
        FOREIGN KEY (mouvement_bien_id) REFERENCES mouvements_biens(id_mouvement),
    CONSTRAINT fk_trajets_vehicule
        FOREIGN KEY (vehicule_id) REFERENCES vehicules(id_bien),
    CONSTRAINT fk_trajets_chauffeur
        FOREIGN KEY (chauffeur_id) REFERENCES chauffeurs(id)
);

-- Idempotence colonnes trajets
ALTER TABLE trajets ADD COLUMN IF NOT EXISTS lat_depart DOUBLE PRECISION;
ALTER TABLE trajets ADD COLUMN IF NOT EXISTS lng_depart DOUBLE PRECISION;
ALTER TABLE trajets ADD COLUMN IF NOT EXISTS lat_arrivee DOUBLE PRECISION;
ALTER TABLE trajets ADD COLUMN IF NOT EXISTS lng_arrivee DOUBLE PRECISION;
ALTER TABLE trajets ADD COLUMN IF NOT EXISTS carburant_consomme_estime DOUBLE PRECISION;
ALTER TABLE trajets ADD COLUMN IF NOT EXISTS source_donnees VARCHAR(50) DEFAULT 'MOBILE';

-- ----------------------------------------------------------------------------
-- 2. INDEX
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_vehicules_immatriculation ON vehicules(immatriculation);

CREATE INDEX IF NOT EXISTS ix_chauffeurs_id              ON chauffeurs(id);
CREATE INDEX IF NOT EXISTS ix_chauffeurs_organisation_id ON chauffeurs(organisation_id);
CREATE INDEX IF NOT EXISTS ix_chauffeurs_utilisateur_id  ON chauffeurs(utilisateur_id);

CREATE INDEX IF NOT EXISTS ix_missions_id                ON missions(id);
CREATE INDEX IF NOT EXISTS ix_missions_organisation_id   ON missions(organisation_id);
CREATE INDEX IF NOT EXISTS ix_missions_projet_id         ON missions(projet_id);
CREATE INDEX IF NOT EXISTS ix_missions_org_statut        ON missions(organisation_id, statut);

CREATE INDEX IF NOT EXISTS ix_affectations_mission_organisation_id ON affectations_mission(organisation_id);
CREATE INDEX IF NOT EXISTS ix_affectations_mission_mission_id      ON affectations_mission(mission_id);
CREATE INDEX IF NOT EXISTS ix_affectations_mission_vehicule_id     ON affectations_mission(vehicule_id);
CREATE INDEX IF NOT EXISTS ix_affectations_mission_chauffeur_id    ON affectations_mission(chauffeur_id);

CREATE INDEX IF NOT EXISTS ix_trajets_organisation_id ON trajets(organisation_id);
CREATE INDEX IF NOT EXISTS ix_trajets_mission_id      ON trajets(mission_id);
CREATE INDEX IF NOT EXISTS ix_trajets_vehicule_id     ON trajets(vehicule_id);
CREATE INDEX IF NOT EXISTS ix_trajets_chauffeur_id    ON trajets(chauffeur_id);

-- Un numéro de permis ne peut exister qu'une fois par organisation
CREATE UNIQUE INDEX IF NOT EXISTS uq_chauffeurs_org_permis
    ON chauffeurs(organisation_id, numero_permis);

-- Un numéro de mission est unique par organisation
CREATE UNIQUE INDEX IF NOT EXISTS uq_missions_org_numero
    ON missions(organisation_id, numero_mission);

-- Un utilisateur ne peut être associé qu'à un seul chauffeur actif par organisation
CREATE UNIQUE INDEX IF NOT EXISTS uq_chauffeur_org_user_actif
    ON chauffeurs(organisation_id, utilisateur_id)
    WHERE utilisateur_id IS NOT NULL AND actif = true;

-- ----------------------------------------------------------------------------
-- 3. CONTRAINTES D'INTÉGRITÉ MÉTIER (garde-fou côté base, en plus du code)
-- ----------------------------------------------------------------------------

-- Suppression indispensable de l'ancienne contrainte UNIQUE GLOBALE sur immatriculation
-- (sinon deux organisations distinctes ne peuvent pas posséder la même plaque)
ALTER TABLE vehicules DROP CONSTRAINT IF EXISTS vehicules_immatriculation_key;

DO $$
BEGIN
    -- Dates cohérentes
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_missions_dates') THEN
        ALTER TABLE missions ADD CONSTRAINT ck_missions_dates
            CHECK (date_debut IS NULL OR date_fin IS NULL OR date_debut <= date_fin);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_affectations_dates') THEN
        ALTER TABLE affectations_mission ADD CONSTRAINT ck_affectations_dates
            CHECK (date_debut < date_fin);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_affectations_ressource') THEN
        ALTER TABLE affectations_mission ADD CONSTRAINT ck_affectations_ressource
            CHECK (vehicule_id IS NOT NULL OR chauffeur_id IS NOT NULL);
    END IF;

    -- Kilométrage
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_trajets_km') THEN
        ALTER TABLE trajets ADD CONSTRAINT ck_trajets_km
            CHECK (
                (kilometrage_debut IS NULL OR kilometrage_debut >= 0)
                AND (kilometrage_fin IS NULL OR kilometrage_debut IS NULL
                     OR kilometrage_fin >= kilometrage_debut)
                AND (distance_km IS NULL OR distance_km >= 0)
            );
    END IF;

    -- Anti-chevauchement VÉHICULE : deux requêtes simultanées ne peuvent pas
    -- réserver le même véhicule sur des périodes qui se recouvrent.
    -- Les affectations ANNULEE et REJETEE sont ignorées.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ex_affectation_vehicule_periode') THEN
        ALTER TABLE affectations_mission ADD CONSTRAINT ex_affectation_vehicule_periode
            EXCLUDE USING gist (
                vehicule_id WITH =,
                tsrange(date_debut, date_fin) WITH &&
            ) WHERE (vehicule_id IS NOT NULL AND statut IS DISTINCT FROM 'ANNULEE' AND statut IS DISTINCT FROM 'REJETEE');
    END IF;

    -- Anti-chevauchement CHAUFFEUR
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ex_affectation_chauffeur_periode') THEN
        ALTER TABLE affectations_mission ADD CONSTRAINT ex_affectation_chauffeur_periode
            EXCLUDE USING gist (
                chauffeur_id WITH =,
                tsrange(date_debut, date_fin) WITH &&
            ) WHERE (chauffeur_id IS NOT NULL AND statut IS DISTINCT FROM 'ANNULEE' AND statut IS DISTINCT FROM 'REJETEE');
    END IF;
END $$;

-- Immatriculation unique PAR ORGANISATION.
-- organisation_id est porté par la table biens (pas par vehicules), donc un
-- index UNIQUE simple est impossible : on utilise un trigger + verrou consultatif.
CREATE OR REPLACE FUNCTION fn_vehicules_immat_unique_par_org() RETURNS trigger AS $$
DECLARE
    v_org INTEGER;
BEGIN
    IF NEW.immatriculation IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT organisation_id INTO v_org FROM biens WHERE id_bien = NEW.id_bien;
    PERFORM pg_advisory_xact_lock(hashtext(COALESCE(v_org::text, '0') || ':' || NEW.immatriculation));
    IF EXISTS (
        SELECT 1
        FROM vehicules v
        JOIN biens b ON b.id_bien = v.id_bien
        WHERE v.immatriculation = NEW.immatriculation
          AND b.organisation_id IS NOT DISTINCT FROM v_org
          AND v.id_bien <> NEW.id_bien
    ) THEN
        RAISE EXCEPTION 'Immatriculation % déjà utilisée dans cette organisation', NEW.immatriculation
            USING ERRCODE = '23505';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_vehicules_immat_unique ON vehicules;
CREATE TRIGGER trg_vehicules_immat_unique
    BEFORE INSERT OR UPDATE OF immatriculation ON vehicules
    FOR EACH ROW EXECUTE FUNCTION fn_vehicules_immat_unique_par_org();

-- ----------------------------------------------------------------------------
-- 4. DONNÉES DE RÉFÉRENCE
-- ----------------------------------------------------------------------------

-- 4.1 TypeBien VEHICULE : INDISPENSABLE, sinon POST /vehicules renvoie
--     "Le TypeBien de code VEHICULE n'est pas configuré".
--     Compte SYSCOHADA 245 = matériel de transport.
INSERT INTO types_biens (libelle, code, compte_comptable, champs_specifiques, description, est_actif)
VALUES (
    'Véhicule', 'VEHICULE', '2450',
    '{"champs": ["categorie","immatriculation","vin","numero_boitier_gps","date_expiration_assurance","date_expiration_visite_technique","date_expiration_permis_transport","capacite_reservoir","consommation_theorique","kilometrage_actuel","prochain_km_maintenance","type_carburant","couleur","nombre_places"]}',
    'Véhicules du parc automobile (voitures, motos, camions, bus)',
    TRUE
)
ON CONFLICT (code) DO UPDATE SET
    compte_comptable = EXCLUDED.compte_comptable,
    champs_specifiques = EXCLUDED.champs_specifiques,
    description = EXCLUDED.description,
    est_actif = EXCLUDED.est_actif;

-- 4.2 Rôles Flotte
INSERT INTO roles (nom, description, actif)
VALUES
    ('CHAUFFEUR', 'Chauffeur de véhicule', TRUE),
    ('LOGISTICIEN', 'Responsable logistique', TRUE),
    ('RESPONSABLE_PROJET', 'Responsable de projet', TRUE)
ON CONFLICT (nom) DO UPDATE SET
    description = EXCLUDED.description,
    actif = EXCLUDED.actif;

-- 4.3 Permissions Flotte
INSERT INTO permissions (nom, description, module, action, actif)
VALUES
    ('ORGANISATION_GERER',     'Gérer les organisations',              'organisation', 'gerer', TRUE),
    ('ORGANISATION_VOIR',      'Consulter les organisations',          'organisation', 'voir', TRUE),
    ('ABONNEMENT_GERER',       'Gérer les abonnements',                'abonnement',   'gerer', TRUE),
    ('ABONNEMENT_VOIR',        'Consulter les abonnements',            'abonnement',   'voir', TRUE),
    ('FACTURATION_GERER',      'Gérer la facturation',                 'facturation',  'gerer', TRUE),
    ('FACTURATION_VOIR',       'Consulter la facturation',             'facturation',  'voir', TRUE),
    ('PROJET_GERER',           'Gérer les projets',                    'projet',       'gerer', TRUE),
    ('PROJET_VOIR',            'Consulter les projets',                'projet',       'voir', TRUE),
    ('WORKFLOW_GERER',         'Gérer les workflows',                  'workflow',     'gerer', TRUE),
    ('WORKFLOW_VOIR',          'Consulter les workflows',              'workflow',     'voir', TRUE),
    ('PERMISSION_GERER',       'Gérer les permissions',                'permission',   'gerer', TRUE),
    ('IMPORT_CSV',             'Exécuter un import CSV',               'import',       'executer', TRUE),
    ('MISSION_CREATE',         'Créer une demande de mission',         'mission',      'create', TRUE),
    ('MISSION_VOIR',           'Consulter les missions',               'mission',      'voir', TRUE),
    ('MISSION_MODIFIER',       'Modifier les missions',                'mission',      'modifier', TRUE),
    ('MISSION_SUPPRIMER',      'Supprimer les missions',               'mission',      'supprimer', TRUE),
    ('MISSION_AFFECTER',       'Affecter les ressources aux missions', 'mission',      'affecter', TRUE),
    ('MISSION_VALIDATE_LOG',   'Valider une mission (logistique)',     'mission',      'validate_log', TRUE),
    ('MISSION_VALIDATE_DG',    'Valider une mission (direction)',      'mission',      'validate_dg', TRUE),
    ('MISSION_CLOSE',          'Clôturer une mission',                 'mission',      'close', TRUE),
    ('CARBURANT_SAISIR',       'Saisir un ravitaillement',             'carburant',    'saisir', TRUE),
    ('CARBURANT_VALIDER',      'Valider un ravitaillement',            'carburant',    'valider', TRUE),
    ('INCIDENT_DECLARER',      'Déclarer un incident véhicule',        'incident',     'declarer', TRUE),
    ('INCIDENT_VALIDER',       'Valider un incident véhicule',         'incident',     'valider', TRUE),
    ('CHAUFFEUR_GERER',        'Gérer les chauffeurs',                 'chauffeur',    'gerer', TRUE),
    ('VEHICULE_VOIR',          'Consulter les véhicules',              'vehicule',     'voir', TRUE),
    ('VEHICULE_CREER',         'Créer les véhicules',                  'vehicule',     'creer', TRUE),
    ('VEHICULE_MODIFIER',      'Modifier les véhicules',               'vehicule',     'modifier', TRUE),
    ('VEHICULE_SUPPRIMER',     'Supprimer les véhicules',              'vehicule',     'supprimer', TRUE),
    ('TRAJET_GERER',           'Gérer les trajets',                     'trajet',       'gerer', TRUE),
    ('RAPPORT_FLOTTE_VOIR',    'Consulter les rapports flotte',        'rapport',      'voir', TRUE),
    ('RAPPORT_FLOTTE_EXPORTER','Exporter les rapports flotte',         'rapport',      'exporter', TRUE),
    ('ALERTE_TRAITER',         'Traiter/ignorer une alerte flotte',    'alerte',       'traiter', TRUE)
ON CONFLICT (nom) DO UPDATE SET
    description = EXCLUDED.description,
    module = EXCLUDED.module,
    action = EXCLUDED.action,
    actif = EXCLUDED.actif;

-- 4.4 Attribution des permissions aux rôles dans role_permissions
-- ADMIN reçoit toutes les permissions
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'ADMIN'
ON CONFLICT DO NOTHING;

-- LOGISTICIEN
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'LOGISTICIEN'
  AND p.nom IN (
    'PROJET_VOIR', 'WORKFLOW_VOIR', 'MISSION_VALIDATE_LOG', 'MISSION_CLOSE',
    'MISSION_VOIR', 'MISSION_MODIFIER', 'MISSION_SUPPRIMER', 'MISSION_AFFECTER',
    'CARBURANT_VALIDER', 'INCIDENT_VALIDER', 'CHAUFFEUR_GERER', 'VEHICULE_VOIR',
    'VEHICULE_CREER', 'VEHICULE_MODIFIER', 'VEHICULE_SUPPRIMER', 'TRAJET_GERER',
    'ALERTE_TRAITER', 'RAPPORT_FLOTTE_VOIR'
  )
ON CONFLICT DO NOTHING;

-- RESPONSABLE_PROJET
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'RESPONSABLE_PROJET'
  AND p.nom IN (
    'PROJET_VOIR', 'MISSION_CREATE', 'RAPPORT_FLOTTE_VOIR'
  )
ON CONFLICT DO NOTHING;

-- CHAUFFEUR
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'CHAUFFEUR'
  AND p.nom IN (
    'CARBURANT_SAISIR', 'INCIDENT_DECLARER'
  )
ON CONFLICT DO NOTHING;

-- DG
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'DG'
  AND p.nom IN (
    'ORGANISATION_VOIR', 'ABONNEMENT_VOIR', 'FACTURATION_VOIR', 'PROJET_VOIR',
    'PROJET_GERER', 'WORKFLOW_VOIR', 'MISSION_VALIDATE_DG', 'MISSION_VOIR',
    'TRAJET_GERER', 'RAPPORT_FLOTTE_VOIR', 'RAPPORT_FLOTTE_EXPORTER', 'ALERTE_TRAITER'
  )
ON CONFLICT DO NOTHING;

-- COMPTABLE
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'COMPTABLE'
  AND p.nom IN (
    'FACTURATION_VOIR', 'RAPPORT_FLOTTE_VOIR', 'VEHICULE_VOIR'
  )
ON CONFLICT DO NOTHING;

-- CAISSE
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'CAISSE'
  AND p.nom IN (
    'RAPPORT_FLOTTE_VOIR'
  )
ON CONFLICT DO NOTHING;

COMMIT;

-- ----------------------------------------------------------------------------
-- 5. CONTRÔLES À LANCER APRÈS L'EXÉCUTION (lecture seule)
-- ----------------------------------------------------------------------------

-- 5.1 Les 5 tables existent-elles ?
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('vehicules','chauffeurs','missions','affectations_mission','trajets')
ORDER BY 1;

-- 5.2 Le type VEHICULE est-il présent ?
SELECT id, code, libelle, est_actif FROM types_biens WHERE code = 'VEHICULE';

-- 5.3 Modules flotte présents et inclus dans les plans (script_ver_02)
SELECT plan_abonnement, module_code, est_inclus
FROM plan_modules
WHERE module_code IN ('VEHICULE','CHAUFFEUR','MISSION','PROJET','TRAJET')
ORDER BY plan_abonnement, module_code;

-- 5.4 Valeur 'MISSION' présente dans l'enum typeworkflow ?
SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
WHERE t.typname = 'typeworkflow';

-- 5.5 Chevauchements déjà présents (à corriger AVANT la section 3 si elle échoue)
SELECT a.id AS aff_1, b.id AS aff_2, a.vehicule_id, a.date_debut, a.date_fin
FROM affectations_mission a
JOIN affectations_mission b
  ON a.vehicule_id = b.vehicule_id AND a.id < b.id
 AND a.date_debut < b.date_fin AND a.date_fin > b.date_debut
WHERE COALESCE(a.statut,'') <> 'ANNULEE' AND COALESCE(a.statut,'') <> 'REJETEE'
  AND COALESCE(b.statut,'') <> 'ANNULEE' AND COALESCE(b.statut,'') <> 'REJETEE';

-- 5.6 Ancienne contrainte UNIQUE globale sur l'immatriculation (doit être vide désormais)
SELECT conname FROM pg_constraint
WHERE conrelid = 'vehicules'::regclass AND contype = 'u';

-- 5.7 Colonne organisation_id sur biens (multi-tenant) et valeurs orphelines
SELECT COUNT(*) AS biens_sans_organisation FROM biens WHERE organisation_id IS NULL;
