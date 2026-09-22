-- ============================================================
-- 09_add_organisation_id_and_unique_constraints.sql
-- Phase 5 Vague 5.22 — Multi-tenant : ajout organisation_id
--                     + correction des contraintes UNIQUE
-- ============================================================
-- ⚠️ IDEMPOTENT — peut être relancé sans erreur
-- ⚠️ À exécuter APRÈS avoir supprimé les anciennes contraintes UNIQUE
-- ============================================================

BEGIN;

-- ============================================================
-- 1. AJOUT COLONNE organisation_id (si absente)
-- ============================================================

-- alertes_vnc
ALTER TABLE alertes_vnc ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_alertes_vnc_organisation_id ON alertes_vnc(organisation_id);

-- besoins
ALTER TABLE besoins ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_besoins_organisation_id ON besoins(organisation_id);

-- centres_cout
ALTER TABLE centres_cout ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_centres_cout_organisation_id ON centres_cout(organisation_id);

-- cessions
ALTER TABLE cessions ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_cessions_organisation_id ON cessions(organisation_id);

-- config_inventaire
ALTER TABLE config_inventaire ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_config_inventaire_organisation_id ON config_inventaire(organisation_id);

-- discussions_concertation
ALTER TABLE discussions_concertation ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_discussions_concertation_organisation_id ON discussions_concertation(organisation_id);

-- messages_concertation
ALTER TABLE messages_concertation ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_messages_concertation_organisation_id ON messages_concertation(organisation_id);

-- validations_concertation
ALTER TABLE validations_concertation ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_validations_concertation_organisation_id ON validations_concertation(organisation_id);

-- fournisseurs
ALTER TABLE fournisseurs ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_fournisseurs_organisation_id ON fournisseurs(organisation_id);

-- fournitures_pieces
ALTER TABLE fournitures_pieces ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_fournitures_pieces_organisation_id ON fournitures_pieces(organisation_id);

-- historique_statuts_ecritures
ALTER TABLE historique_statuts_ecritures ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_historique_statuts_ecritures_organisation_id ON historique_statuts_ecritures(organisation_id);

-- lignes_besoin
ALTER TABLE lignes_besoin ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_lignes_besoin_organisation_id ON lignes_besoin(organisation_id);

-- localisations
ALTER TABLE localisations ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_localisations_organisation_id ON localisations(organisation_id);

-- ordres_remplacement
ALTER TABLE ordres_remplacement ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_ordres_remplacement_organisation_id ON ordres_remplacement(organisation_id);

-- projections_investissement
ALTER TABLE projections_investissement ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_projections_investissement_organisation_id ON projections_investissement(organisation_id);

-- regles_amortissement
ALTER TABLE regles_amortissement ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_regles_amortissement_organisation_id ON regles_amortissement(organisation_id);

-- regles_historique
ALTER TABLE regles_historique ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_regles_historique_organisation_id ON regles_historique(organisation_id);

-- ============================================================
-- 2. AJOUT FOREIGN KEY (si absente)
-- ============================================================

DO $$
BEGIN
    -- alertes_vnc
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_alertes_vnc_organisation') THEN
        ALTER TABLE alertes_vnc ADD CONSTRAINT fk_alertes_vnc_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- besoins
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_besoins_organisation') THEN
        ALTER TABLE besoins ADD CONSTRAINT fk_besoins_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- centres_cout
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_centres_cout_organisation') THEN
        ALTER TABLE centres_cout ADD CONSTRAINT fk_centres_cout_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- cessions
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cessions_organisation') THEN
        ALTER TABLE cessions ADD CONSTRAINT fk_cessions_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- config_inventaire
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_config_inventaire_organisation') THEN
        ALTER TABLE config_inventaire ADD CONSTRAINT fk_config_inventaire_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- discussions_concertation
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_discussions_concertation_organisation') THEN
        ALTER TABLE discussions_concertation ADD CONSTRAINT fk_discussions_concertation_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- messages_concertation
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_messages_concertation_organisation') THEN
        ALTER TABLE messages_concertation ADD CONSTRAINT fk_messages_concertation_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- validations_concertation
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_validations_concertation_organisation') THEN
        ALTER TABLE validations_concertation ADD CONSTRAINT fk_validations_concertation_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- fournisseurs
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fournisseurs_organisation') THEN
        ALTER TABLE fournisseurs ADD CONSTRAINT fk_fournisseurs_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- fournitures_pieces
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fournitures_pieces_organisation') THEN
        ALTER TABLE fournitures_pieces ADD CONSTRAINT fk_fournitures_pieces_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- historique_statuts_ecritures
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_historique_statuts_ecritures_organisation') THEN
        ALTER TABLE historique_statuts_ecritures ADD CONSTRAINT fk_historique_statuts_ecritures_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- lignes_besoin
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_lignes_besoin_organisation') THEN
        ALTER TABLE lignes_besoin ADD CONSTRAINT fk_lignes_besoin_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- localisations
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_localisations_organisation') THEN
        ALTER TABLE localisations ADD CONSTRAINT fk_localisations_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- ordres_remplacement
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ordres_remplacement_organisation') THEN
        ALTER TABLE ordres_remplacement ADD CONSTRAINT fk_ordres_remplacement_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- projections_investissement
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projections_investissement_organisation') THEN
        ALTER TABLE projections_investissement ADD CONSTRAINT fk_projections_investissement_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- regles_amortissement
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_regles_amortissement_organisation') THEN
        ALTER TABLE regles_amortissement ADD CONSTRAINT fk_regles_amortissement_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    -- regles_historique
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_regles_historique_organisation') THEN
        ALTER TABLE regles_historique ADD CONSTRAINT fk_regles_historique_organisation 
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ============================================================
-- 3. SUPPRESSION DES ANCIENNES CONTRAINTES UNIQUE
-- ============================================================

-- besoins.numero_demande (unique simple à supprimer)
ALTER TABLE besoins DROP CONSTRAINT IF EXISTS besoins_numero_demande_key;

-- centres_cout.code
ALTER TABLE centres_cout DROP CONSTRAINT IF EXISTS centres_cout_code_key;

-- localisations.nom_localisation
ALTER TABLE localisations DROP CONSTRAINT IF EXISTS localisations_nom_localisation_key;

-- regles_amortissement.categorie_bien
ALTER TABLE regles_amortissement DROP CONSTRAINT IF EXISTS regles_amortissement_categorie_bien_key;

-- ============================================================
-- 4. AJOUT DES NOUVELLES CONTRAINTES UNIQUE COMPOSITES
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_besoin_org_numero_demande') THEN
        ALTER TABLE besoins ADD CONSTRAINT uq_besoin_org_numero_demande 
            UNIQUE (organisation_id, numero_demande);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_centre_cout_org_code') THEN
        ALTER TABLE centres_cout ADD CONSTRAINT uq_centre_cout_org_code 
            UNIQUE (organisation_id, code);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_localisation_org_nom') THEN
        ALTER TABLE localisations ADD CONSTRAINT uq_localisation_org_nom 
            UNIQUE (organisation_id, nom_localisation);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_regle_amort_org_categorie') THEN
        ALTER TABLE regles_amortissement ADD CONSTRAINT uq_regle_amort_org_categorie 
            UNIQUE (organisation_id, categorie_bien);
    END IF;
END $$;

-- ============================================================
-- 5. BACKFILL organisation_id (récupération depuis les parents)
-- ============================================================

-- alertes_vnc ← biens
UPDATE alertes_vnc a SET organisation_id = b.organisation_id
FROM biens b WHERE a.bien_id = b.id_bien AND a.organisation_id IS NULL;

-- besoins ← pannes ← biens
UPDATE besoins be SET organisation_id = b.organisation_id
FROM pannes p JOIN biens b ON p.id_bien = b.id_bien
WHERE be.id_panne = p.id_panne AND be.organisation_id IS NULL;

-- cessions ← biens
UPDATE cessions c SET organisation_id = b.organisation_id
FROM biens b WHERE c.id_bien = b.id_bien AND c.organisation_id IS NULL;

-- discussions_concertation ← biens
UPDATE discussions_concertation d SET organisation_id = b.organisation_id
FROM biens b WHERE d.id_bien = b.id_bien AND d.organisation_id IS NULL;

-- messages_concertation ← discussions_concertation
UPDATE messages_concertation m SET organisation_id = d.organisation_id
FROM discussions_concertation d
WHERE m.id_discussion = d.id AND m.organisation_id IS NULL;

-- validations_concertation ← discussions_concertation
UPDATE validations_concertation v SET organisation_id = d.organisation_id
FROM discussions_concertation d
WHERE v.id_discussion = d.id AND v.organisation_id IS NULL;

-- fournitures_pieces ← besoins
UPDATE fournitures_pieces f SET organisation_id = b.organisation_id
FROM besoins b WHERE f.id_besoin = b.id_besoin AND f.organisation_id IS NULL;

-- lignes_besoin ← besoins
UPDATE lignes_besoin l SET organisation_id = b.organisation_id
FROM besoins b WHERE l.id_besoin = b.id_besoin AND l.organisation_id IS NULL;

-- historique_statuts_ecritures ← ecritures_comptables
UPDATE historique_statuts_ecritures h SET organisation_id = e.organisation_id
FROM ecritures_comptables e
WHERE h.id_ecriture = e.id_ecriture AND h.organisation_id IS NULL;

-- ordres_remplacement ← biens
UPDATE ordres_remplacement o SET organisation_id = b.organisation_id
FROM biens b WHERE o.bien_id = b.id_bien AND o.organisation_id IS NULL;

-- projections_investissement ← biens
UPDATE projections_investissement p SET organisation_id = b.organisation_id
FROM biens b WHERE p.bien_id = b.id_bien AND p.organisation_id IS NULL;

-- regles_historique ← regles_amortissement
UPDATE regles_historique rh SET organisation_id = ra.organisation_id
FROM regles_amortissement ra
WHERE rh.id_regle = ra.id_regle AND rh.organisation_id IS NULL;

-- ⚠️ Tables sans backfill automatique possible (entités racines) :
-- - centres_cout, config_inventaire, fournisseurs, localisations, regles_amortissement
-- → À backfiller manuellement selon la logique métier (par défaut : organisation #1)
-- Exemple :
-- UPDATE centres_cout SET organisation_id = 1 WHERE organisation_id IS NULL;
-- UPDATE fournisseurs SET organisation_id = 1 WHERE organisation_id IS NULL;
-- UPDATE localisations SET organisation_id = 1 WHERE organisation_id IS NULL;
-- UPDATE regles_amortissement SET organisation_id = 1 WHERE organisation_id IS NULL;
-- UPDATE config_inventaire SET organisation_id = 1 WHERE organisation_id IS NULL;

COMMIT;

-- ============================================================
-- 6. VÉRIFICATION POST-MIGRATION
-- ============================================================

-- Vérifier que toutes les tables ont la colonne
SELECT 
    table_name,
    COUNT(*) FILTER (WHERE column_name = 'organisation_id') AS a_colonne
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'alertes_vnc', 'besoins', 'centres_cout', 'cessions',
      'config_inventaire', 'discussions_concertation', 'messages_concertation',
      'validations_concertation', 'fournisseurs', 'fournitures_pieces',
      'historique_statuts_ecritures', 'lignes_besoin', 'localisations',
      'ordres_remplacement', 'projections_investissement',
      'regles_amortissement', 'regles_historique'
  )
GROUP BY table_name
ORDER BY table_name;

-- Vérifier les nouvelles contraintes UNIQUE
SELECT conname, conrelid::regclass AS table_name
FROM pg_constraint
WHERE conname IN (
    'uq_besoin_org_numero_demande',
    'uq_centre_cout_org_code',
    'uq_localisation_org_nom',
    'uq_regle_amort_org_categorie'
)
ORDER BY conname;


----=======================migrations 02=========================


BEGIN;

-- 1. AJOUT COLONNE organisation_id
ALTER TABLE pieces_rechange ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_pieces_rechange_organisation_id ON pieces_rechange(organisation_id);

ALTER TABLE pieces_justificatives ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_pieces_justificatives_organisation_id ON pieces_justificatives(organisation_id);

-- 2. FOREIGN KEYS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_pieces_rechange_organisation') THEN
        ALTER TABLE pieces_rechange ADD CONSTRAINT fk_pieces_rechange_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_pieces_justificatives_organisation') THEN
        ALTER TABLE pieces_justificatives ADD CONSTRAINT fk_pieces_justificatives_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 3. SUPPRESSION ANCIENNE CONTRAINTE UNIQUE
ALTER TABLE pieces_rechange DROP CONSTRAINT IF EXISTS pieces_rechange_numero_serie_key;

-- 4. NOUVELLE CONTRAINTE COMPOSITE
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_piece_rechange_org_numero_serie') THEN
        ALTER TABLE pieces_rechange ADD CONSTRAINT uq_piece_rechange_org_numero_serie
            UNIQUE (organisation_id, numero_serie);
    END IF;
END $$;

-- 5. BACKFILL pieces_justificatives via mouvements_caisse → caisses
UPDATE pieces_justificatives p
SET organisation_id = c.organisation_id
FROM mouvements_caisse m
JOIN caisses c ON c.id_caisse = m.id_caisse
WHERE p.id_mouvement = m.id_mouvement AND p.organisation_id IS NULL;

-- 6. BACKFILL pieces_rechange (2 sources possibles)
--   a) via lignes_besoin → besoins
UPDATE pieces_rechange pr
SET organisation_id = be.organisation_id
FROM lignes_besoin lb
JOIN besoins be ON lb.id_besoin = be.id_besoin
WHERE lb.id_piece = pr.id_piece AND pr.organisation_id IS NULL AND be.organisation_id IS NOT NULL;

--   b) via fournitures_pieces
UPDATE pieces_rechange pr
SET organisation_id = fp.organisation_id
FROM fournitures_pieces fp
WHERE fp.id_piece = pr.id_piece AND pr.organisation_id IS NULL AND fp.organisation_id IS NOT NULL;

COMMIT;

-- Vérification
SELECT 'pieces_rechange' AS table_name,
       COUNT(*) FILTER (WHERE organisation_id IS NULL) AS null_org,
       COUNT(*) AS total
FROM pieces_rechange
UNION ALL
SELECT 'pieces_justificatives' AS table_name,
       COUNT(*) FILTER (WHERE organisation_id IS NULL) AS null_org,
       COUNT(*) AS total
FROM pieces_justificatives;


---==================migrantion 03========================
-- ============================================================
-- 09c_add_organisation_id_mouvements_caisse.sql
-- Phase 5 Vague 5.22 — Correctif : MouvementCaisse multi-tenant
-- ============================================================
-- ⚠️ IDEMPOTENT
-- ============================================================

BEGIN;

-- 1. AJOUT COLONNE organisation_id
ALTER TABLE mouvements_caisse ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_mouvements_caisse_organisation_id ON mouvements_caisse(organisation_id);

-- 2. FOREIGN KEY
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_mouvements_caisse_organisation') THEN
        ALTER TABLE mouvements_caisse ADD CONSTRAINT fk_mouvements_caisse_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 3. SUPPRESSION ANCIENNE CONTRAINTE UNIQUE (numero_piece)
ALTER TABLE mouvements_caisse DROP CONSTRAINT IF EXISTS mouvements_caisse_numero_piece_key;

-- 4. NOUVELLE CONTRAINTE COMPOSITE
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_mvt_caisse_org_numero_piece') THEN
        ALTER TABLE mouvements_caisse ADD CONSTRAINT uq_mvt_caisse_org_numero_piece
            UNIQUE (organisation_id, numero_piece);
    END IF;
END $$;

-- 5. BACKFILL via caisses
UPDATE mouvements_caisse m
SET organisation_id = c.organisation_id
FROM caisses c
WHERE m.id_caisse = c.id_caisse AND m.organisation_id IS NULL;

COMMIT;

-- Vérification
SELECT 'mouvements_caisse' AS table_name,
       COUNT(*) FILTER (WHERE organisation_id IS NULL) AS null_org,
       COUNT(*) AS total
FROM mouvements_caisse;

SELECT conname, conrelid::regclass AS table_name
FROM pg_constraint
WHERE conname = 'uq_mvt_caisse_org_numero_piece';

--==================migration 04========================
-- ============================================================
-- 09d_add_organisation_id_decisions_ia.sql
-- Phase 5 Vague 5.22 — Table decisions_ia non couverte à l'Étape 1
-- ============================================================

BEGIN;

-- Ajout colonne (idempotent)
ALTER TABLE decisions_ia ADD COLUMN IF NOT EXISTS organisation_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_decisions_ia_organisation_id ON decisions_ia(organisation_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_decisions_ia_organisation') THEN
        ALTER TABLE decisions_ia ADD CONSTRAINT fk_decisions_ia_organisation
            FOREIGN KEY (organisation_id) REFERENCES organisations(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Backfill : via bien_id
UPDATE decisions_ia d
SET organisation_id = b.organisation_id
FROM biens b
WHERE d.id_bien = b.id_bien AND d.organisation_id IS NULL;

-- Backfill : via piece_id
UPDATE decisions_ia d
SET organisation_id = p.organisation_id
FROM pieces_rechange p
WHERE d.id_piece = p.id_piece AND d.organisation_id IS NULL AND p.organisation_id IS NOT NULL;

COMMIT;

-- Vérification
SELECT 'decisions_ia' AS table_name,
       COUNT(*) FILTER (WHERE organisation_id IS NULL) AS null_org,
       COUNT(*) AS total
FROM decisions_ia;