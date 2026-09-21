-- ============================================================================
-- Phase 2 — Script 1/4
-- Création de la table organisation_role_permissions
-- Rôle : stocker les surcharges de permissions par ONG
-- Compatible : PostgreSQL 12+
-- Idempotent : oui (IF NOT EXISTS)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Table principale
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS organisation_role_permissions (
    id                  SERIAL       PRIMARY KEY,
    organisation_id     INTEGER      NOT NULL,
    id_role             INTEGER      NOT NULL,
    id_permission       INTEGER      NOT NULL,
    accorde             BOOLEAN      NOT NULL DEFAULT TRUE,
    date_modification   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Clés étrangères avec CASCADE
    CONSTRAINT fk_org_role_perm_organisation
        FOREIGN KEY (organisation_id)
        REFERENCES organisations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_org_role_perm_role
        FOREIGN KEY (id_role)
        REFERENCES roles(id_role)
        ON DELETE CASCADE,

    CONSTRAINT fk_org_role_perm_permission
        FOREIGN KEY (id_permission)
        REFERENCES permissions(id_permission)
        ON DELETE CASCADE,

    -- Unicité : un seul override par triplet (org, role, permission)
    CONSTRAINT uq_org_role_permission
        UNIQUE (organisation_id, id_role, id_permission)
);

-- ----------------------------------------------------------------------------
-- Index pour les requêtes fréquentes
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_org_role_perm_organisation
    ON organisation_role_permissions(organisation_id);

CREATE INDEX IF NOT EXISTS ix_org_role_perm_role
    ON organisation_role_permissions(id_role);

CREATE INDEX IF NOT EXISTS ix_org_role_perm_permission
    ON organisation_role_permissions(id_permission);

-- Index composite pour la résolution de permission (le plus utilisé)
CREATE INDEX IF NOT EXISTS ix_org_role_perm_lookup
    ON organisation_role_permissions(organisation_id, id_role, id_permission);

-- ----------------------------------------------------------------------------
-- Commentaires (documentation en base)
-- ----------------------------------------------------------------------------
COMMENT ON TABLE  organisation_role_permissions
    IS 'Surcharges de permissions par ONG (override de role_permissions)';

COMMENT ON COLUMN organisation_role_permissions.accorde
    IS 'TRUE = permission accordée, FALSE = permission retirée. Absent = hérite de role_permissions.';

COMMENT ON COLUMN organisation_role_permissions.date_modification
    IS 'Date de la dernière modification de cet override';

COMMIT;



-----------=============second script =============----------------
-- ============================================================================
-- Phase 2 — Script 2/4
-- Ajout de la colonne doit_changer_mot_de_passe sur utilisateurs
-- Rôle : forcer le changement de mot de passe à la 1ère connexion de l'admin ONG
-- Compatible : PostgreSQL 12+
-- Idempotent : oui (IF NOT EXISTS)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Ajout de la colonne
-- ----------------------------------------------------------------------------
ALTER TABLE utilisateurs
    ADD COLUMN IF NOT EXISTS doit_changer_mot_de_passe BOOLEAN NOT NULL DEFAULT FALSE;

-- ----------------------------------------------------------------------------
-- Commentaire
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN utilisateurs.doit_changer_mot_de_passe
    IS 'Si TRUE, force le changement de mot de passe à la prochaine connexion';

-- ----------------------------------------------------------------------------
-- Valeur par défaut pour les utilisateurs existants (sécurité)
-- On ne force PAS le changement pour les utilisateurs historiques
-- ----------------------------------------------------------------------------
UPDATE utilisateurs
SET doit_changer_mot_de_passe = FALSE
WHERE doit_changer_mot_de_passe IS NULL;

COMMIT;

---===============script creation taux d'echange============
-- ============================================================================
-- Phase 4 — Script 1/1
-- Création de la table taux_change (multi-devises)
-- Rôle : stocker les taux de change quotidiens par ONG
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS taux_change (
    id                  SERIAL       PRIMARY KEY,
    organisation_id     INTEGER      NOT NULL,
    devise_source       VARCHAR(3)   NOT NULL,
    devise_cible        VARCHAR(3)   NOT NULL,
    taux                NUMERIC(15,6) NOT NULL,
    date_taux           DATE         NOT NULL,
    source              VARCHAR(50)  DEFAULT 'MANUEL',
    date_creation       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id      INTEGER      NULL,

    CONSTRAINT fk_taux_change_organisation
        FOREIGN KEY (organisation_id)
        REFERENCES organisations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_taux_change_utilisateur
        FOREIGN KEY (utilisateur_id)
        REFERENCES utilisateurs(id)
        ON DELETE SET NULL,

    CONSTRAINT uq_taux_change_org_devises_date
        UNIQUE (organisation_id, devise_source, devise_cible, date_taux)
);

CREATE INDEX IF NOT EXISTS ix_taux_change_org_devises_date
    ON taux_change(organisation_id, devise_source, devise_cible, date_taux DESC);

CREATE INDEX IF NOT EXISTS ix_taux_change_organisation
    ON taux_change(organisation_id);

COMMENT ON TABLE taux_change
    IS 'Taux de change quotidiens par ONG (multi-devises)';

COMMENT ON COLUMN taux_change.taux
    IS 'Taux de conversion : 1 devise_source = X devise_cible';

COMMIT;


------==================update utilisateur====
UPDATE utilisateurs
SET organisation_id = NULL
WHERE id = 1;


SELECT id, email, organisation_id, role_id FROM utilisateurs WHERE id = 1;


-- ============================================================================
-- Phase 5 — Script SQL 6/1
-- Création des tables modules + plan_modules (référentiel SaaS)
-- Compatible : PostgreSQL 12+
-- Idempotent : oui (IF NOT EXISTS)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Table 1 : modules (référentiel central)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS modules (
    code                VARCHAR(50)   PRIMARY KEY,
    libelle             VARCHAR(200)  NOT NULL,
    description         TEXT          NULL,
    icone               VARCHAR(100)  NULL,
    categorie           VARCHAR(50)   NULL,
    ordre_affichage     INTEGER       NOT NULL DEFAULT 100,
    actif               BOOLEAN       NOT NULL DEFAULT TRUE,
    est_systeme         BOOLEAN       NOT NULL DEFAULT FALSE,
    date_creation       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_modification   TIMESTAMP     NULL,
    utilisateur_id      INTEGER       NULL,

    CONSTRAINT fk_modules_utilisateur
        FOREIGN KEY (utilisateur_id)
        REFERENCES utilisateurs(id)
        ON DELETE SET NULL
);

COMMENT ON TABLE modules
    IS 'Référentiel des modules SaaS activables par ONG';

COMMENT ON COLUMN modules.code
    IS 'Code unique du module (ex: MISSION, GPS_TRACKING)';

COMMENT ON COLUMN modules.est_systeme
    IS 'TRUE = module non supprimable (utilisé par le code)';

COMMENT ON COLUMN modules.categorie
    IS 'Catégorie fonctionnelle : IMMOBILISATION, FLOTTE, SAAS, MOBILE';

-- ----------------------------------------------------------------------------
-- Table 2 : plan_modules (cartographie plan ↔ module)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plan_modules (
    id                  SERIAL        PRIMARY KEY,
    plan_abonnement     VARCHAR(20)   NOT NULL,
    module_code         VARCHAR(50)   NOT NULL,
    est_inclus          BOOLEAN       NOT NULL DEFAULT TRUE,
    date_creation       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_plan_modules_module
        FOREIGN KEY (module_code)
        REFERENCES modules(code)
        ON DELETE CASCADE,

    CONSTRAINT uq_plan_modules
        UNIQUE (plan_abonnement, module_code),

    CONSTRAINT ck_plan_abonnement
        CHECK (plan_abonnement IN ('BASIC', 'PRO', 'ENTERPRISE'))
);

COMMENT ON TABLE plan_modules
    IS 'Modules inclus par défaut dans chaque plan d''abonnement';

-- ----------------------------------------------------------------------------
-- Index pour les requêtes fréquentes
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_modules_actif
    ON modules(actif);

CREATE INDEX IF NOT EXISTS ix_modules_categorie
    ON modules(categorie);

CREATE INDEX IF NOT EXISTS ix_modules_ordre
    ON modules(ordre_affichage);

CREATE INDEX IF NOT EXISTS ix_plan_modules_plan
    ON plan_modules(plan_abonnement);

CREATE INDEX IF NOT EXISTS ix_plan_modules_module
    ON plan_modules(module_code);

COMMIT;


-- ============================================================================
-- Phase 5 — Script SQL 7/1
-- Insertion des 18 modules + cartographie BASIC / PRO / ENTERPRISE
-- Idempotent : oui (ON CONFLICT DO NOTHING)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Les 18 modules
-- ----------------------------------------------------------------------------
INSERT INTO modules (code, libelle, description, icone, categorie, ordre_affichage, est_systeme) VALUES
    ('IMMOBILISATION',       'Immobilisations',      'Gestion des biens et du patrimoine',              'CubeIcon',                    'IMMOBILISATION', 10,  TRUE),
    ('MAINTENANCE',          'Maintenances',         'Planification et suivi des maintenances',         'WrenchScrewdriverIcon',       'IMMOBILISATION', 20,  TRUE),
    ('VEHICULE',             'Véhicules',            'Gestion du parc automobile',                      'TruckIcon',                   'FLOTTE',         30,  TRUE),
    ('CHAUFFEUR',            'Chauffeurs',           'Gestion des chauffeurs et permis',                'UserIcon',                    'FLOTTE',         40,  TRUE),
    ('MISSION',              'Missions',             'Demande, validation et suivi des missions',       'MapPinIcon',                  'FLOTTE',         50,  TRUE),
    ('CARBURANT',            'Carburant',            'Ravitaillements et consommation',                 'BanknotesIcon',               'FLOTTE',         60,  TRUE),
    ('IMPORT_CSV',           'Import CSV',           'Import de données depuis Excel/CSV',              'ArrowUpTrayIcon',             'SAAS',           70,  TRUE),
    ('PROJET',               'Projets bailleurs',    'Gestion des projets et budgets bailleurs',        'FolderOpenIcon',              'SAAS',           80,  TRUE),
    ('TRAJET',               'Trajets',              'Suivi des trajets opérationnels',                 'ArrowRightIcon',              'FLOTTE',         90,  TRUE),
    ('INCIDENT',             'Incidents',            'Déclaration d''incidents et pannes',              'ExclamationTriangleIcon',     'FLOTTE',         100, TRUE),
    ('WORKFLOW_PERSONNALISE','Workflow personnalisé','Configuration des circuits de validation par ONG','AdjustmentsHorizontalIcon',   'SAAS',           110, TRUE),
    ('ALERTES_AUTOMATIQUES', 'Alertes automatiques', 'Alertes temps réel (vitesse, zones, carburant)',  'BellAlertIcon',               'FLOTTE',         120, TRUE),
    ('MOBILE_PWA',           'PWA chauffeur',        'Application mobile offline-first pour chauffeurs','ComputerDesktopIcon',         'MOBILE',         130, TRUE),
    ('GPS_TRACKING',         'GPS mobile',           'Suivi GPS via le téléphone du chauffeur',         'MapPinIcon',                  'FLOTTE',         140, TRUE),
    ('REPORTING_AVANCE',     'Rapports avancés',     'Rapports et exports pour bailleurs',              'DocumentChartBarIcon',        'SAAS',           150, TRUE),
    ('IOT_TELEMETRIE',       'Boîtiers IoT',         'Intégration des boîtiers GPS physiques',          'CpuChipIcon',                 'FLOTTE',         160, TRUE),
    ('MULTI_DEVISES',        'Multi-devises',        'Gestion USD / CDF / autres devises',              'CurrencyDollarIcon',          'SAAS',           170, TRUE),
    ('API_EXTERNE',          'API externe',          'API pour intégrations tierces',                   'LinkIcon',                    'SAAS',           180, TRUE)
ON CONFLICT (code) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. Cartographie BASIC (7 modules)
-- ----------------------------------------------------------------------------
INSERT INTO plan_modules (plan_abonnement, module_code, est_inclus) VALUES
    ('BASIC', 'IMMOBILISATION',        TRUE),
    ('BASIC', 'MAINTENANCE',           TRUE),
    ('BASIC', 'VEHICULE',              TRUE),
    ('BASIC', 'CHAUFFEUR',             TRUE),
    ('BASIC', 'MISSION',               TRUE),
    ('BASIC', 'CARBURANT',             TRUE),
    ('BASIC', 'IMPORT_CSV',            TRUE)
ON CONFLICT (plan_abonnement, module_code) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 3. Cartographie PRO (15 modules)
-- ----------------------------------------------------------------------------
INSERT INTO plan_modules (plan_abonnement, module_code, est_inclus) VALUES
    ('PRO', 'IMMOBILISATION',         TRUE),
    ('PRO', 'MAINTENANCE',            TRUE),
    ('PRO', 'VEHICULE',               TRUE),
    ('PRO', 'CHAUFFEUR',              TRUE),
    ('PRO', 'MISSION',                TRUE),
    ('PRO', 'CARBURANT',              TRUE),
    ('PRO', 'IMPORT_CSV',             TRUE),
    ('PRO', 'PROJET',                 TRUE),
    ('PRO', 'TRAJET',                 TRUE),
    ('PRO', 'INCIDENT',               TRUE),
    ('PRO', 'WORKFLOW_PERSONNALISE',  TRUE),
    ('PRO', 'ALERTES_AUTOMATIQUES',   TRUE),
    ('PRO', 'MOBILE_PWA',             TRUE),
    ('PRO', 'GPS_TRACKING',           TRUE),
    ('PRO', 'REPORTING_AVANCE',       TRUE)
ON CONFLICT (plan_abonnement, module_code) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. Cartographie ENTERPRISE (18 modules — tous)
-- ----------------------------------------------------------------------------
INSERT INTO plan_modules (plan_abonnement, module_code, est_inclus) VALUES
    ('ENTERPRISE', 'IMMOBILISATION',         TRUE),
    ('ENTERPRISE', 'MAINTENANCE',            TRUE),
    ('ENTERPRISE', 'VEHICULE',               TRUE),
    ('ENTERPRISE', 'CHAUFFEUR',              TRUE),
    ('ENTERPRISE', 'MISSION',                TRUE),
    ('ENTERPRISE', 'CARBURANT',              TRUE),
    ('ENTERPRISE', 'IMPORT_CSV',             TRUE),
    ('ENTERPRISE', 'PROJET',                 TRUE),
    ('ENTERPRISE', 'TRAJET',                 TRUE),
    ('ENTERPRISE', 'INCIDENT',               TRUE),
    ('ENTERPRISE', 'WORKFLOW_PERSONNALISE',  TRUE),
    ('ENTERPRISE', 'ALERTES_AUTOMATIQUES',   TRUE),
    ('ENTERPRISE', 'MOBILE_PWA',             TRUE),
    ('ENTERPRISE', 'GPS_TRACKING',           TRUE),
    ('ENTERPRISE', 'REPORTING_AVANCE',       TRUE),
    ('ENTERPRISE', 'IOT_TELEMETRIE',         TRUE),
    ('ENTERPRISE', 'MULTI_DEVISES',          TRUE),
    ('ENTERPRISE', 'API_EXTERNE',            TRUE)
ON CONFLICT (plan_abonnement, module_code) DO NOTHING;

COMMIT;