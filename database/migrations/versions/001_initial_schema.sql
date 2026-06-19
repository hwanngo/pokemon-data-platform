-- 001_initial_schema
--
-- The full initial schema now lives in database/initdb/schema.sql (the single
-- source of truth, kept in sync with src/models/). It is applied by init.sh
-- before any migration runs, so this migration is intentionally a no-op and is
-- retained only to preserve the schema_migrations version history.
--
-- Add future schema changes as new, higher-numbered migration files.

SELECT 1;
