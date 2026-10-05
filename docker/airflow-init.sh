#!/usr/bin/env bash
set -euo pipefail

airflow db migrate

# Passing arguments through the environment preserves spaces and shell metacharacters.
# Airflow reports an existing user as a nonzero result; only that case is idempotent.
output_file=$(mktemp)
trap 'rm -f "$output_file"' EXIT
if airflow users create \
    -r Admin \
    -u "$AIRFLOW_ADMIN_USERNAME" \
    -p "$AIRFLOW_ADMIN_PASSWORD" \
    -e "$AIRFLOW_ADMIN_EMAIL" \
    -f "$AIRFLOW_ADMIN_FIRSTNAME" \
    -l "$AIRFLOW_ADMIN_LASTNAME" >"$output_file" 2>&1; then
    echo "Airflow administrator created."
elif grep -Eiq '(user|username) .*already exists|already exists.*(user|username)' "$output_file"; then
    echo "Airflow administrator already exists."
else
    echo "Airflow administrator creation failed." >&2
    exit 1
fi

airflow pools set pokeapi_mirror "$MIRROR_POOL_SLOTS" 'Throttle concurrent PokeAPI mirror tasks'
