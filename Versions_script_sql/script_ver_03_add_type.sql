--ajpoutes des type sur le typeworkflow

-- 1. Ajout de BESOIN
ALTER TYPE typeworkflow ADD VALUE IF NOT EXISTS 'BESOIN';

-- 2. Ajout de CESSION
ALTER TYPE typeworkflow ADD VALUE IF NOT EXISTS 'CESSION';




---------attribution des id_organisation aux ecriture comptables

-- 1. Diagnostic AVANT le script (à noter pour comparaison)
SELECT 
    COUNT(*) AS total_ecritures,
    COUNT(organisation_id) AS avec_organisation,
    COUNT(*) - COUNT(organisation_id) AS sans_organisation
FROM ecritures_comptables;
-- Résultat attendu : total = X, avec_organisation = 0, sans_organisation = X

-- 2. LE BACKFILL PROPREMENT DIT
UPDATE ecritures_comptables e
SET organisation_id = b.organisation_id
FROM biens b
WHERE e.id_bien = b.id_bien
  AND e.organisation_id IS NULL; 

-- 3. Vérification APRÈS le script
SELECT 
    COUNT(*) AS total_ecritures,
    COUNT(organisation_id) AS avec_organisation,
    COUNT(*) - COUNT(organisation_id) AS sans_organisation
FROM ecritures_comptables;
-- Résultat attendu : total = X, avec_organisation = X, sans_organisation = 0

--4. Répartition par ONG (pour vérifier la cohérence)
SELECT 
    COALESCE(b.organisation_id, -1) AS organisation_id,
    COUNT(e.id_ecriture) AS nb_ecritures
FROM ecritures_comptables e
LEFT JOIN biens b ON b.id_bien = e.id_bien
GROUP BY COALESCE(b.organisation_id, -1)
ORDER BY organisation_id;