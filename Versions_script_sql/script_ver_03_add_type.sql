--ajpoutes des type sur le typeworkflow

-- 1. Ajout de BESOIN
ALTER TYPE typeworkflow ADD VALUE IF NOT EXISTS 'BESOIN';

-- 2. Ajout de CESSION
ALTER TYPE typeworkflow ADD VALUE IF NOT EXISTS 'CESSION';