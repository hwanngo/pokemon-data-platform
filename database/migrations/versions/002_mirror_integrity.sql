-- Forward-only upgrade for databases initialized before the mirror integrity work.
-- Safe to rerun after schema.sql; all existing data is retained.
ALTER TABLE pokemon ADD COLUMN IF NOT EXISTS is_default BOOLEAN;
ALTER TABLE pokemon ADD COLUMN IF NOT EXISTS order_num INTEGER;
ALTER TABLE pokemon ADD COLUMN IF NOT EXISTS species_id INTEGER;
UPDATE pokemon SET is_default = TRUE WHERE is_default IS NULL;
ALTER TABLE pokemon ALTER COLUMN is_default SET NOT NULL;

ALTER TABLE pokemon_moves ADD COLUMN IF NOT EXISTS version_group_id INTEGER;
UPDATE pokemon_moves SET level_learned_at = 0 WHERE level_learned_at IS NULL;
UPDATE pokemon_moves SET learn_method = 'unknown' WHERE learn_method IS NULL;
ALTER TABLE pokemon_moves ALTER COLUMN level_learned_at SET NOT NULL;
ALTER TABLE pokemon_moves ALTER COLUMN learn_method SET NOT NULL;
ALTER TABLE pokemon_moves DROP CONSTRAINT IF EXISTS pokemon_moves_pokemon_id_move_id_learn_method_key;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_pokemon_moves_provenance') THEN
        ALTER TABLE pokemon_moves ADD CONSTRAINT uq_pokemon_moves_provenance
            UNIQUE (pokemon_id, move_id, version_group_id, learn_method, level_learned_at);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_pokemon_species') THEN
        ALTER TABLE pokemon ADD CONSTRAINT fk_pokemon_species
            FOREIGN KEY (species_id) REFERENCES pokemon_species (id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_pokemon_moves_version_group') THEN
        ALTER TABLE pokemon_moves ADD CONSTRAINT fk_pokemon_moves_version_group
            FOREIGN KEY (version_group_id) REFERENCES version_groups (id);
    END IF;
END $$;

ALTER TABLE api_resource ADD COLUMN IF NOT EXISTS source_fetched_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE api_resource ADD COLUMN IF NOT EXISTS loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE api_resource ADD COLUMN IF NOT EXISTS is_present BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS idx_pokemon_species ON pokemon (species_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_moves_version_group ON pokemon_moves (version_group_id);
CREATE TABLE IF NOT EXISTS mirror_resource_runs (
    run_id VARCHAR(36) PRIMARY KEY, resource_type VARCHAR(64) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(16) NOT NULL, attempted INTEGER NOT NULL,
    succeeded INTEGER NOT NULL, failed INTEGER NOT NULL, failed_ids JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mirror_run_resource_completed
    ON mirror_resource_runs (resource_type, completed_at);
