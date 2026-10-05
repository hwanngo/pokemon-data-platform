"""Fresh and forward-only upgrades against disposable PostgreSQL databases.

The test is gated so local pytest never touches a configured database. CI
supplies an ephemeral PostgreSQL service and opts in explicitly.
"""

import os
import subprocess
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.getenv("POKEDATA_CI_POSTGRES") != "1",
    reason="requires an explicitly opted-in, disposable PostgreSQL service",
)


def _connect(database: str):
    return psycopg2.connect(dbname=database)


def _migrate(database: str) -> None:
    env = {**os.environ, "DATABASE_DIR": str(ROOT / "database"), "POSTGRES_DB": database}
    subprocess.run(  # noqa: S603 - fixed, repository-owned migration script
        ["/bin/sh", str(ROOT / "database" / "migrate.sh")],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def disposable_database():
    name = f"pokedata_ci_{uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        yield name
    finally:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


def test_fresh_database_has_schema_roles_and_repeatable_migrations(disposable_database):
    name = disposable_database
    _migrate(name)
    _migrate(name)
    with closing(_connect(name)) as connection, connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        assert [row[0] for row in cursor.fetchall()] == [
            "001_initial_schema",
            "002_mirror_integrity",
        ]
        cursor.execute("SELECT to_regclass('public.mirror_resource_runs') IS NOT NULL")
        assert cursor.fetchone()[0]
        cursor.execute("SELECT has_table_privilege('pokemon_reader', 'pokemon', 'SELECT')")
        assert cursor.fetchone()[0]
        cursor.execute("SELECT has_table_privilege('pokemon_reader', 'pokemon', 'INSERT')")
        assert not cursor.fetchone()[0]
        cursor.execute("SELECT has_table_privilege('pokemon_writer', 'pokemon', 'INSERT')")
        assert cursor.fetchone()[0]
        cursor.execute(
            "SELECT has_database_privilege('airflow_service', current_database(), 'CONNECT')"
        )
        assert not cursor.fetchone()[0]
        cursor.execute("SELECT has_database_privilege('pokemon_reader', 'airflow_meta', 'CONNECT')")
        assert not cursor.fetchone()[0]


def test_legacy_pokemon_rows_survive_forward_migration(disposable_database):
    name = disposable_database
    with closing(_connect(name)) as connection, connection, connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE pokemon (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                height INTEGER NOT NULL,
                weight INTEGER NOT NULL,
                base_experience INTEGER
            )
        """)
        cursor.execute("""
            INSERT INTO pokemon (id, name, height, weight, base_experience)
            VALUES (1, 'bulbasaur', 7, 69, 64)
        """)
    _migrate(name)
    with closing(_connect(name)) as connection, connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT name, height, weight, base_experience, is_default, species_id "
            "FROM pokemon WHERE id = 1"
        )
        assert cursor.fetchone() == ("bulbasaur", 7, 69, 64, True, None)
        cursor.execute("""
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'pokemon'::regclass AND conname = 'fk_pokemon_species'
        """)
        assert cursor.fetchone() == (1,)
