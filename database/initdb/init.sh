#!/bin/sh
set -eu

# PostgreSQL runs this only on a fresh data directory. Existing volumes use
# database/migrate.sh via the app-migrate Compose service.
DATABASE_DIR=/database sh /database/migrate.sh
