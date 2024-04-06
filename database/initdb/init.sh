#!/bin/bash
set -e

# Run base schema
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/schema.sql

# Create migrations table if it doesn't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version VARCHAR(255) PRIMARY KEY,
        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
EOSQL

# Run all migrations in order
for migration in /docker-entrypoint-initdb.d/migrations/versions/*.sql; do
    if [ -f "$migration" ]; then
        version=$(basename "$migration" .sql)
        if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM schema_migrations WHERE version = '$version'" | grep -q 1; then
            echo "Applying migration $version..."
            psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$migration"
            psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "INSERT INTO schema_migrations (version) VALUES ('$version')"
        fi
    fi
done

echo "Database initialization and migrations completed successfully!"