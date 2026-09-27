-- À exécuter manuellement dans pgAdmin AVANT le déploiement du nouveau backend.
-- Schéma inspecté : public.organisations. Aucun champ existant n'est modifié.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.organisations
    ADD COLUMN IF NOT EXISTS sigle VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS forme_juridique VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS rccm VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS id_national VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS numero_impot VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS adresse VARCHAR(500) NULL,
    ADD COLUMN IF NOT EXISTS ville VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS province VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS pays VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS telephone VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS email_contact VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS site_web VARCHAR(500) NULL,
    ADD COLUMN IF NOT EXISTS logo_url VARCHAR(1000) NULL,
    ADD COLUMN IF NOT EXISTS logo_public_id VARCHAR(255) NULL;
COMMIT;
