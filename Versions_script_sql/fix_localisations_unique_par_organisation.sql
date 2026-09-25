-- Correction ciblée : conserver l'unicité par ONG, retirer l'ancien index global.
-- Aucune localisation n'est supprimée ou renommée. Script rejouable.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'localisations'::regclass
          AND conname = 'uq_localisation_org_nom'
          AND contype = 'u'
    ) THEN
        ALTER TABLE localisations ADD CONSTRAINT uq_localisation_org_nom
            UNIQUE (organisation_id, nom_localisation);
    END IF;
END $$;
ALTER TABLE localisations DROP CONSTRAINT IF EXISTS localisations_nom_localisation_key;
DROP INDEX IF EXISTS ix_localisations_nom_localisation;
CREATE INDEX ix_localisations_nom_localisation ON localisations (nom_localisation);
COMMIT;
