-- Pokémon Data Analytics Platform — base schema.
-- This file is the single source of truth for the database structure and is
-- kept in sync with the SQLAlchemy models under src/models/.
-- It is executed once by database/initdb/init.sh before any migrations run.

-- ---------------------------------------------------------------------------
-- Core entities (ids come from PokéAPI, so they are explicit INTEGER PKs).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pokemon (
    id              INTEGER PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    height          INTEGER      NOT NULL,
    weight          INTEGER      NOT NULL,
    base_experience INTEGER,
    is_default      BOOLEAN      NOT NULL,
    order_num       INTEGER
);

CREATE TABLE IF NOT EXISTS types (
    id   INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS abilities (
    id           INTEGER PRIMARY KEY,
    -- display names are not unique in PokéAPI (e.g. two "As One" abilities); id is the key.
    name         VARCHAR(100) NOT NULL,
    effect_text  TEXT,
    short_effect TEXT
);

CREATE TABLE IF NOT EXISTS moves (
    id           INTEGER PRIMARY KEY,
    name         VARCHAR(100) NOT NULL UNIQUE,
    power        INTEGER,
    pp           INTEGER,
    accuracy     INTEGER,
    type_id      INTEGER REFERENCES types (id),
    damage_class VARCHAR(50)
);

-- ---------------------------------------------------------------------------
-- Stats & relationships (surrogate SERIAL PKs).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pokemon_stats (
    id         SERIAL PRIMARY KEY,
    pokemon_id INTEGER     NOT NULL REFERENCES pokemon (id),
    stat_name  VARCHAR(50) NOT NULL,
    base_value INTEGER     NOT NULL,
    UNIQUE (pokemon_id, stat_name)
);

CREATE TABLE IF NOT EXISTS pokemon_types (
    id         SERIAL PRIMARY KEY,
    pokemon_id INTEGER NOT NULL REFERENCES pokemon (id),
    type_id    INTEGER NOT NULL REFERENCES types (id),
    slot       INTEGER NOT NULL,
    UNIQUE (pokemon_id, slot)
);

CREATE TABLE IF NOT EXISTS type_effectiveness (
    id              SERIAL PRIMARY KEY,
    attack_type_id  INTEGER       NOT NULL REFERENCES types (id),
    defense_type_id INTEGER       NOT NULL REFERENCES types (id),
    effectiveness   NUMERIC(3, 2) NOT NULL,
    UNIQUE (attack_type_id, defense_type_id)
);

CREATE TABLE IF NOT EXISTS pokemon_abilities (
    id         SERIAL PRIMARY KEY,
    pokemon_id INTEGER NOT NULL REFERENCES pokemon (id),
    ability_id INTEGER NOT NULL REFERENCES abilities (id),
    is_hidden  BOOLEAN NOT NULL,
    slot       INTEGER NOT NULL,
    UNIQUE (pokemon_id, ability_id)
);

CREATE TABLE IF NOT EXISTS pokemon_moves (
    id               SERIAL PRIMARY KEY,
    pokemon_id       INTEGER NOT NULL REFERENCES pokemon (id),
    move_id          INTEGER NOT NULL REFERENCES moves (id),
    level_learned_at INTEGER,
    learn_method     VARCHAR(50),
    UNIQUE (pokemon_id, move_id, learn_method)
);

-- ---------------------------------------------------------------------------
-- Indexes for join/filter performance on foreign keys.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_pokemon_stats_pokemon_id     ON pokemon_stats (pokemon_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_types_pokemon_id     ON pokemon_types (pokemon_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_types_type_id        ON pokemon_types (type_id);
CREATE INDEX IF NOT EXISTS idx_type_eff_attack              ON type_effectiveness (attack_type_id);
CREATE INDEX IF NOT EXISTS idx_type_eff_defense             ON type_effectiveness (defense_type_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_abilities_pokemon_id ON pokemon_abilities (pokemon_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_abilities_ability_id ON pokemon_abilities (ability_id);
CREATE INDEX IF NOT EXISTS idx_moves_type_id                ON moves (type_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_moves_pokemon_id     ON pokemon_moves (pokemon_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_moves_move_id        ON pokemon_moves (move_id);

-- ===========================================================================
-- PokéAPI full mirror (generic engine — see src/ingestion/mirror.py).
-- JSONB tail: every resource not promoted to a relational table below.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS api_resource (
    resource_type VARCHAR(64)  NOT NULL,
    id            INTEGER       NOT NULL,
    name          VARCHAR(128),
    data          JSONB         NOT NULL,
    fetched_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (resource_type, id)
);
CREATE INDEX IF NOT EXISTS idx_api_resource_name ON api_resource (resource_type, name);
CREATE INDEX IF NOT EXISTS idx_api_resource_data ON api_resource USING GIN (data);

-- --- Relational core --------------------------------------------------------

CREATE TABLE IF NOT EXISTS regions (
    id                 INTEGER PRIMARY KEY,
    name               VARCHAR(100) NOT NULL,
    main_generation_id INTEGER  -- bare: region<->generation is circular
);

CREATE TABLE IF NOT EXISTS generations (
    id               INTEGER PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    main_region_id   INTEGER,  -- bare: circular with regions
    main_region_name VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS version_groups (
    id            INTEGER PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    order_num     INTEGER,
    generation_id INTEGER REFERENCES generations (id)
);

CREATE TABLE IF NOT EXISTS versions (
    id               INTEGER PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    version_group_id INTEGER REFERENCES version_groups (id)
);

CREATE TABLE IF NOT EXISTS pokedexes (
    id             INTEGER PRIMARY KEY,
    name           VARCHAR(255) NOT NULL,
    is_main_series BOOLEAN      NOT NULL,
    region_id      INTEGER REFERENCES regions (id)
);

CREATE TABLE IF NOT EXISTS item_categories (
    id        INTEGER PRIMARY KEY,
    name      VARCHAR(255) NOT NULL,
    pocket_id INTEGER  -- item-pocket lives in the JSONB tail
);

CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    cost            INTEGER,
    fling_power     INTEGER,
    fling_effect_id INTEGER,  -- item-fling-effect lives in the JSONB tail
    category_id     INTEGER REFERENCES item_categories (id),
    sprite_default  TEXT
);

CREATE TABLE IF NOT EXISTS berries (
    id                 INTEGER PRIMARY KEY,
    name               VARCHAR(100) NOT NULL,
    growth_time        INTEGER,
    max_harvest        INTEGER,
    natural_gift_power INTEGER,
    size               INTEGER,
    smoothness         INTEGER,
    soil_dryness       INTEGER,
    firmness           VARCHAR(50),
    natural_gift_type  VARCHAR(50),
    item_id            INTEGER REFERENCES items (id)
);

CREATE TABLE IF NOT EXISTS machines (
    id               INTEGER PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    item_id          INTEGER REFERENCES items (id),
    move_id          INTEGER,  -- bare: decouples machines from the moves load order
    version_group_id INTEGER REFERENCES version_groups (id)
);

CREATE TABLE IF NOT EXISTS locations (
    id        INTEGER PRIMARY KEY,
    name      VARCHAR(100) NOT NULL,
    region_id INTEGER REFERENCES regions (id)
);

CREATE TABLE IF NOT EXISTS location_areas (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    game_index  INTEGER,
    location_id INTEGER REFERENCES locations (id)
);

CREATE TABLE IF NOT EXISTS pokemon_species (
    id                      INTEGER PRIMARY KEY,
    name                    VARCHAR(100) NOT NULL,
    order_num               INTEGER,
    gender_rate             INTEGER,
    capture_rate            INTEGER,
    base_happiness          INTEGER,
    hatch_counter           INTEGER,
    is_baby                 BOOLEAN,
    is_legendary            BOOLEAN,
    is_mythical             BOOLEAN,
    has_gender_differences  BOOLEAN,
    forms_switchable        BOOLEAN,
    generation_id           INTEGER REFERENCES generations (id),
    evolution_chain_id      INTEGER,  -- evolution-chain (tree) lives in the JSONB tail
    evolves_from_species_id INTEGER,
    growth_rate             VARCHAR(50),
    color                   VARCHAR(50),
    shape                   VARCHAR(50),
    habitat                 VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS egg_groups (
    id   INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS natures (
    id             INTEGER PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    decreased_stat VARCHAR(50),
    increased_stat VARCHAR(50),
    hates_flavor   VARCHAR(50),
    likes_flavor   VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS contest_types (
    id           INTEGER PRIMARY KEY,
    name         VARCHAR(50) NOT NULL,
    berry_flavor VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_items_category      ON items (category_id);
CREATE INDEX IF NOT EXISTS idx_berries_item        ON berries (item_id);
CREATE INDEX IF NOT EXISTS idx_machines_item       ON machines (item_id);
CREATE INDEX IF NOT EXISTS idx_machines_vg         ON machines (version_group_id);
CREATE INDEX IF NOT EXISTS idx_versions_vg         ON versions (version_group_id);
CREATE INDEX IF NOT EXISTS idx_version_groups_gen  ON version_groups (generation_id);
CREATE INDEX IF NOT EXISTS idx_locations_region    ON locations (region_id);
CREATE INDEX IF NOT EXISTS idx_location_areas_loc  ON location_areas (location_id);
CREATE INDEX IF NOT EXISTS idx_species_generation  ON pokemon_species (generation_id);
