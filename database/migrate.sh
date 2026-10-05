#!/bin/sh
set -eu

# Run as the application schema owner. Airflow metadata is a separate database.
db_dir=${DATABASE_DIR:-/database}
db_name=${POSTGRES_DB:-pokemon_data}
db_user=${POSTGRES_USER:-postgres}
if [ -f "$db_dir/initdb/schema.sql" ]; then
    init_dir="$db_dir/initdb"
else
    init_dir="$db_dir"
fi

# Compose runs one app-migrate service before application services start.
psql -X -v ON_ERROR_STOP=1 --username "$db_user" --dbname "$db_name" \
    -f "$init_dir/schema.sql"
psql -X -v ON_ERROR_STOP=1 --username "$db_user" --dbname "$db_name" \
    -c 'CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)'

for migration in "$db_dir"/migrations/versions/*.sql; do
    [ -f "$migration" ] || continue
    version=$(basename "$migration" .sql)
    applied=$(psql -X -v ON_ERROR_STOP=1 --username "$db_user" --dbname "$db_name" \
        -v version="$version" -tA -c "SELECT 1 FROM schema_migrations WHERE version = '$version'")
    if [ "$applied" != 1 ]; then
        echo "Applying application migration $version"
        psql -X -v ON_ERROR_STOP=1 --single-transaction --username "$db_user" \
            --dbname "$db_name" -f "$migration" \
            -c "INSERT INTO schema_migrations (version) VALUES ('$version')"
    fi
done

if [ -n "${APP_READER_PASSWORD:-}" ] && [ -n "${APP_WRITER_PASSWORD:-}" ] && [ -n "${AIRFLOW_DB_PASSWORD:-}" ]; then
    psql -X -v ON_ERROR_STOP=1 --username "$db_user" --dbname "$db_name" \
        -v reader_password="$APP_READER_PASSWORD" \
        -v writer_password="$APP_WRITER_PASSWORD" \
        -v airflow_password="$AIRFLOW_DB_PASSWORD" \
        -f "$init_dir/roles.sql"
fi
echo 'Application schema migrations completed.'
