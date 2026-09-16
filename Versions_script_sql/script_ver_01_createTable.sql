-- ============================================================================
-- CRÉATION DE LA TABLE organisations (racine multi-tenant)
-- ============================================================================

BEGIN;

-- Création des types ENUM
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'planabonnement') THEN
        CREATE TYPE planabonnement AS ENUM ('BASIC', 'PRO', 'ENTERPRISE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'statutorganisation') THEN
        CREATE TYPE statutorganisation AS ENUM ('ACTIF', 'SUSPENDU', 'EXPIRE');
    END IF;
END $$;

-- Création de la table organisations
CREATE TABLE IF NOT EXISTS organisations (
    id                  SERIAL PRIMARY KEY,
    nom                 VARCHAR(200) NOT NULL,
    code                VARCHAR(50) NOT NULL UNIQUE,
    email_admin         VARCHAR(200) NOT NULL,
    plan_abonnement     planabonnement NOT NULL DEFAULT 'BASIC',
    quota_vehicules     INTEGER NOT NULL DEFAULT 10,
    quota_chauffeurs    INTEGER NOT NULL DEFAULT 10,
    quota_missions_mois INTEGER NOT NULL DEFAULT 50,
    devise              VARCHAR(3) NOT NULL DEFAULT 'USD',
    date_debut          DATE,
    date_fin            DATE,
    statut              statutorganisation NOT NULL DEFAULT 'ACTIF',
    parametres_json     JSON DEFAULT '{}'::json,
    date_creation       TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    date_modification   TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS ix_organisations_id ON organisations(id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_organisations_code ON organisations(code);

-- Commentaires
COMMENT ON TABLE organisations IS 'Organisations multi-tenant (ONG propriétaires)';
COMMENT ON COLUMN organisations.code IS 'Code court (ex: OKAPI, MSF)';
COMMENT ON COLUMN organisations.parametres_json IS 'Workflow, seuils, configs diverses';

COMMIT;

-- Vérification
SELECT 'Table organisations créée' AS statut,
       COUNT(*) AS nb_tables
FROM information_schema.tables
WHERE table_name = 'organisations';



-- ============================================================================
-- CRÉATION DE LA TABLE projets (dépend de organisations)
-- ============================================================================

BEGIN;

-- Création de la table projets
CREATE TABLE IF NOT EXISTS projets (
    id              SERIAL PRIMARY KEY,
    organisation_id INTEGER NOT NULL,
    code            VARCHAR(50) NOT NULL,
    nom             VARCHAR(200) NOT NULL,
    bailleur        VARCHAR(200),
    budget_annuel   NUMERIC(14, 2) DEFAULT 0.0,
    devise          VARCHAR(3) NOT NULL DEFAULT 'USD',
    date_debut      DATE,
    date_fin        DATE,
    est_actif       BOOLEAN NOT NULL DEFAULT TRUE,
    date_creation   TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),

    -- Contrainte FK vers organisations
    CONSTRAINT fk_projets_organisation
        FOREIGN KEY (organisation_id)
        REFERENCES organisations(id)
        ON DELETE CASCADE,

    -- Contrainte d'unicité : un code projet unique par organisation
    CONSTRAINT uq_projet_code_org
        UNIQUE (organisation_id, code)
);

-- Index
CREATE INDEX IF NOT EXISTS ix_projets_id ON projets(id);
CREATE INDEX IF NOT EXISTS ix_projets_organisation_id ON projets(organisation_id);
CREATE INDEX IF NOT EXISTS ix_projets_code ON projets(code);

-- Commentaires
COMMENT ON TABLE projets IS 'Projets bailleurs associés à une organisation';
COMMENT ON COLUMN projets.organisation_id IS 'Organisation propriétaire (multi-tenant)';
COMMENT ON COLUMN projets.code IS 'Code unique par organisation';

COMMIT;

-- Vérification
SELECT 'Table projets créée' AS statut,
       COUNT(*) AS nb_tables
FROM information_schema.tables
WHERE table_name = 'projets';


-- ============================================================================
-- INSERTION D'UNE ORGANISATION PAR DÉFAUT (ONG OKAPI)
-- À ADAPTER selon votre contexte réel
-- ============================================================================

BEGIN;

INSERT INTO organisations (
    nom,
    code,
    email_admin,
    plan_abonnement,
    quota_vehicules,
    quota_chauffeurs,
    quota_missions_mois,
    devise,
    statut
)
VALUES (
    'ONG OKAPI',
    'OKAPI',
    'admin@okapi.org',
    'ENTERPRISE',
    500,
    500,
    1000,
    'USD',
    'ACTIF'
)
ON CONFLICT (code) DO NOTHING;

COMMIT;

-- Vérification
SELECT id, nom, code, plan_abonnement, statut
FROM organisations;


---===========================================================Migrations version 1 pour ajouts des id
-- ============================================================================
-- SPRINT 0 — MULTI-TENANT OKAPI FLOTTE (version sans transaction globale)
-- ============================================================================

-- ============================================================================
-- ÉTAPE 0 — VÉRIFICATIONS PRÉALABLES
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'organisations') THEN
        RAISE EXCEPTION 'Table "organisations" introuvable. Créez d''abord les modèles Organisation et Projet.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projets') THEN
        RAISE EXCEPTION 'Table "projets" introuvable. Créez d''abord le modèle Projet.';
    END IF;
    RAISE NOTICE 'Vérifications préalables : OK';
END $$;

-- ============================================================================
-- ÉTAPE 1 — AJOUT DE organisation_id SUR 13 TABLES
-- ============================================================================

-- 1.1 utilisateurs
ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN utilisateurs.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_utilisateurs_organisation') THEN
        ALTER TABLE utilisateurs ADD CONSTRAINT fk_utilisateurs_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_utilisateurs_organisation_id ON utilisateurs(organisation_id);

-- 1.2 biens
ALTER TABLE biens ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN biens.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_biens_organisation') THEN
        ALTER TABLE biens ADD CONSTRAINT fk_biens_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_biens_organisation_id ON biens(organisation_id);

-- 1.3 budgets
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN budgets.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_budgets_organisation') THEN
        ALTER TABLE budgets ADD CONSTRAINT fk_budgets_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_budgets_organisation_id ON budgets(organisation_id);

-- 1.4 besoins
ALTER TABLE besoins ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN besoins.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_besoins_organisation') THEN
        ALTER TABLE besoins ADD CONSTRAINT fk_besoins_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_besoins_organisation_id ON besoins(organisation_id);

-- 1.5 mouvements_biens
ALTER TABLE mouvements_biens ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN mouvements_biens.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_mouvements_biens_organisation') THEN
        ALTER TABLE mouvements_biens ADD CONSTRAINT fk_mouvements_biens_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_mouvements_biens_organisation_id ON mouvements_biens(organisation_id);

-- 1.6 maintenances
ALTER TABLE maintenances ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN maintenances.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_maintenances_organisation') THEN
        ALTER TABLE maintenances ADD CONSTRAINT fk_maintenances_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_maintenances_organisation_id ON maintenances(organisation_id);

-- 1.7 pannes
ALTER TABLE pannes ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN pannes.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_pannes_organisation') THEN
        ALTER TABLE pannes ADD CONSTRAINT fk_pannes_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_pannes_organisation_id ON pannes(organisation_id);

-- 1.8 amortissements
ALTER TABLE amortissements ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN amortissements.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_amortissements_organisation') THEN
        ALTER TABLE amortissements ADD CONSTRAINT fk_amortissements_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_amortissements_organisation_id ON amortissements(organisation_id);

-- 1.9 ecritures_comptables
ALTER TABLE ecritures_comptables ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN ecritures_comptables.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ecritures_comptables_organisation') THEN
        ALTER TABLE ecritures_comptables ADD CONSTRAINT fk_ecritures_comptables_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_ecritures_comptables_organisation_id ON ecritures_comptables(organisation_id);

-- 1.10 caisses
ALTER TABLE caisses ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN caisses.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_caisses_organisation') THEN
        ALTER TABLE caisses ADD CONSTRAINT fk_caisses_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_caisses_organisation_id ON caisses(organisation_id);

-- 1.11 notifications
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN notifications.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_notifications_organisation') THEN
        ALTER TABLE notifications ADD CONSTRAINT fk_notifications_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_notifications_organisation_id ON notifications(organisation_id);

-- 1.12 journal_evenements_immobilisation
ALTER TABLE journal_evenements_immobilisation ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN journal_evenements_immobilisation.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_journal_evt_immo_organisation') THEN
        ALTER TABLE journal_evenements_immobilisation ADD CONSTRAINT fk_journal_evt_immo_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_journal_evt_immo_organisation_id ON journal_evenements_immobilisation(organisation_id);

-- 1.13 validations
ALTER TABLE validations ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
COMMENT ON COLUMN validations.organisation_id IS 'Multi-tenant : ONG propriétaire';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_validations_organisation') THEN
        ALTER TABLE validations ADD CONSTRAINT fk_validations_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_validations_organisation_id ON validations(organisation_id);

-- ============================================================================
-- ÉTAPE 2 — AJOUT DE id_projet SUR 3 TABLES
-- ============================================================================

-- 2.1 budgets
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS id_projet INTEGER;
COMMENT ON COLUMN budgets.id_projet IS 'Projet bailleur associé (Sprint 0)';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_budgets_projet') THEN
        ALTER TABLE budgets ADD CONSTRAINT fk_budgets_projet
            FOREIGN KEY (id_projet) REFERENCES projets(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_budgets_id_projet ON budgets(id_projet);

-- 2.2 besoins
ALTER TABLE besoins ADD COLUMN IF NOT EXISTS id_projet INTEGER;
COMMENT ON COLUMN besoins.id_projet IS 'Projet bailleur associé (Sprint 0)';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_besoins_projet') THEN
        ALTER TABLE besoins ADD CONSTRAINT fk_besoins_projet
            FOREIGN KEY (id_projet) REFERENCES projets(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_besoins_id_projet ON besoins(id_projet);

-- 2.3 mouvements_biens
ALTER TABLE mouvements_biens ADD COLUMN IF NOT EXISTS id_projet INTEGER;
COMMENT ON COLUMN mouvements_biens.id_projet IS 'Projet bailleur associé (Sprint 0)';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_mouvements_biens_projet') THEN
        ALTER TABLE mouvements_biens ADD CONSTRAINT fk_mouvements_biens_projet
            FOREIGN KEY (id_projet) REFERENCES projets(id) ON DELETE SET NULL;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_mouvements_biens_id_projet ON mouvements_biens(id_projet);

-- ============================================================================
-- ÉTAPE 3 — VALIDATION FINALE
-- ============================================================================
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM information_schema.columns
    WHERE column_name = 'organisation_id'
      AND table_name IN (
          'utilisateurs', 'biens', 'budgets', 'besoins', 'mouvements_biens',
          'maintenances', 'pannes', 'amortissements', 'ecritures_comptables',
          'caisses', 'notifications', 'journal_evenements_immobilisation', 'validations'
      );
    RAISE NOTICE 'Colonnes organisation_id créées : % / 13', v_count;

    SELECT COUNT(*) INTO v_count
    FROM information_schema.columns
    WHERE column_name = 'id_projet'
      AND table_name IN ('budgets', 'besoins', 'mouvements_biens');
    RAISE NOTICE 'Colonnes id_projet créées : % / 3', v_count;

    RAISE NOTICE '✅ Migration Sprint 0 terminée avec succès.';
END $$;


---===============Remplacement des id_par celle de l'organisation 

BEGIN;

UPDATE utilisateurs                        SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE biens                               SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE budgets                             SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE besoins                             SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE mouvements_biens                    SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE maintenances                        SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE pannes                              SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE amortissements                      SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE ecritures_comptables                SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE caisses                             SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE notifications                       SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE journal_evenements_immobilisation   SET organisation_id = 1 WHERE organisation_id IS NULL;
UPDATE validations                         SET organisation_id = 1 WHERE organisation_id IS NULL;

COMMIT;



--------==============creation table abonnement
-- ============================================================================
-- CRÉATION DE LA TABLE abonnements_facturation
-- Dépend de : organisations
-- ============================================================================

BEGIN;

-- Création du type ENUM pour le statut de paiement
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'statutpaiement') THEN
        CREATE TYPE statutpaiement AS ENUM ('EN_ATTENTE', 'PAYE', 'RETARD');
    END IF;
END $$;

-- Création de la table
CREATE TABLE IF NOT EXISTS abonnements_facturation (
    id                  SERIAL PRIMARY KEY,
    organisation_id     INTEGER NOT NULL,
    periode             VARCHAR(20) NOT NULL,
    montant             NUMERIC(12, 2) NOT NULL,
    devise              VARCHAR(3) NOT NULL DEFAULT 'USD',
    statut_paiement     statutpaiement NOT NULL DEFAULT 'EN_ATTENTE',
    date_echeance       DATE,
    date_paiement       TIMESTAMP WITHOUT TIME ZONE,
    facture_url         VARCHAR,
    date_creation       TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),

    -- Contrainte FK
    CONSTRAINT fk_abonnements_facturation_organisation
        FOREIGN KEY (organisation_id)
        REFERENCES organisations(id)
        ON DELETE CASCADE
);

-- Index
CREATE INDEX IF NOT EXISTS ix_abonnements_facturation_id
    ON abonnements_facturation(id);

CREATE INDEX IF NOT EXISTS ix_abonnements_facturation_organisation_id
    ON abonnements_facturation(organisation_id);

-- Commentaires
COMMENT ON TABLE abonnements_facturation
    IS 'Facturation des abonnements SaaS par organisation';
COMMENT ON COLUMN abonnements_facturation.organisation_id
    IS 'Organisation facturée (multi-tenant)';
COMMENT ON COLUMN abonnements_facturation.periode
    IS 'Ex: 2026-01, 2026-Q1';
COMMENT ON COLUMN abonnements_facturation.facture_url
    IS 'Lien Cloudinary PDF';

COMMIT;

-- Vérification
SELECT 'Table abonnements_facturation créée' AS statut,
       COUNT(*) AS nb_tables
FROM information_schema.tables
WHERE table_name = 'abonnements_facturation';


----========================creation table work
-- ============================================================================
-- CRÉATION DE LA TABLE workflow_etapes
-- Dépend de : organisations
-- ============================================================================

BEGIN;

-- Création du type ENUM pour le type de workflow
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'typeworkflow') THEN
        CREATE TYPE typeworkflow AS ENUM ('MISSION', 'RAVITAILLEMENT', 'INCIDENT');
    END IF;
END $$;

-- Création de la table
CREATE TABLE IF NOT EXISTS workflow_etapes (
    id                  SERIAL PRIMARY KEY,
    organisation_id     INTEGER NOT NULL,
    type_workflow       typeworkflow NOT NULL,
    ordre               INTEGER NOT NULL,
    role_requis         VARCHAR(50),
    permission_requise  VARCHAR(50),
    condition           JSON,
    est_optionnelle     BOOLEAN NOT NULL DEFAULT FALSE,
    actif               BOOLEAN NOT NULL DEFAULT TRUE,
    date_creation       TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),

    -- Contrainte FK
    CONSTRAINT fk_workflow_etapes_organisation
        FOREIGN KEY (organisation_id)
        REFERENCES organisations(id)
        ON DELETE CASCADE
);

-- Index
CREATE INDEX IF NOT EXISTS ix_workflow_etapes_id
    ON workflow_etapes(id);

CREATE INDEX IF NOT EXISTS ix_workflow_etapes_organisation_id
    ON workflow_etapes(organisation_id);

CREATE INDEX IF NOT EXISTS ix_workflow_etapes_type_workflow
    ON workflow_etapes(type_workflow);

-- Commentaires
COMMENT ON TABLE workflow_etapes
    IS 'Étapes de workflow configurables par organisation';
COMMENT ON COLUMN workflow_etapes.ordre
    IS 'Étape 1, 2, 3…';
COMMENT ON COLUMN workflow_etapes.role_requis
    IS 'Rôle qui valide cette étape';
COMMENT ON COLUMN workflow_etapes.permission_requise
    IS 'Permission granulaire';
COMMENT ON COLUMN workflow_etapes.condition
    IS 'Ex: {"seuil_montant": 1000}';

COMMIT;

-- Vérification
SELECT 'Table workflow_etapes créée' AS statut,
       COUNT(*) AS nb_tables
FROM information_schema.tables
WHERE table_name = 'workflow_etapes';


---==============reaschronyse le role id

-- Resynchroniser la séquence roles
SELECT setval(
    'roles_id_role_seq',
    (SELECT MAX(id_role) FROM roles),
    true
);

-- Resynchroniser la séquence permissions (par sécurité)
SELECT setval(
    'permissions_id_permission_seq',
    (SELECT MAX(id_permission) FROM permissions),
    true
);


----==========mise a jour de permissions 

BEGIN;

UPDATE permissions SET module='mission',   action='create'       WHERE nom='MISSION_CREATE';
UPDATE permissions SET module='mission',   action='validate_log' WHERE nom='MISSION_VALIDATE_LOG';
UPDATE permissions SET module='mission',   action='validate_dg'  WHERE nom='MISSION_VALIDATE_DG';
UPDATE permissions SET module='mission',   action='close'        WHERE nom='MISSION_CLOSE';
UPDATE permissions SET module='carburant', action='saisir'       WHERE nom='CARBURANT_SAISIR';
UPDATE permissions SET module='carburant', action='valider'      WHERE nom='CARBURANT_VALIDER';
UPDATE permissions SET module='incident',  action='declarer'     WHERE nom='INCIDENT_DECLARER';
UPDATE permissions SET module='incident',  action='valider'      WHERE nom='INCIDENT_VALIDER';
UPDATE permissions SET module='chauffeur', action='gerer'        WHERE nom='CHAUFFEUR_GERER';
UPDATE permissions SET module='projet',    action='gerer'        WHERE nom='PROJET_GERER';
UPDATE permissions SET module='rapport',   action='voir'         WHERE nom='RAPPORT_FLOTTE_VOIR';
UPDATE permissions SET module='rapport',   action='exporter'     WHERE nom='RAPPORT_FLOTTE_EXPORTER';
UPDATE permissions SET module='alerte',    action='traiter'      WHERE nom='ALERTE_TRAITER';

COMMIT;



-------====AJOUT SUR LES PERMISSIONS
-- 1. S'assurer que la permission WORKFLOW_VOIR existe
INSERT INTO permissions (nom, description, module, action, actif)
VALUES ('WORKFLOW_VOIR', 'Consulter les workflows', 'workflow', 'voir', true)
ON CONFLICT (nom) DO NOTHING;

-- 2. L'attribuer au rôle ADMIN
INSERT INTO role_permissions (id_role, id_permission)
SELECT r.id_role, p.id_permission
FROM roles r, permissions p
WHERE r.nom = 'ADMIN' AND p.nom = 'WORKFLOW_VOIR'
ON CONFLICT DO NOTHING;

-- 3. Vérification
SELECT r.nom AS role, p.nom AS permission
FROM roles r
JOIN role_permissions rp ON rp.id_role = r.id_role
JOIN permissions p ON p.id_permission = rp.id_permission
WHERE r.nom = 'ADMIN' 
  AND p.nom IN ('WORKFLOW_VOIR', 'WORKFLOW_GERER');