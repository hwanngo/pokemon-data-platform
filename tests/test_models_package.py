"""Importing the models package alone must register every table on Base.metadata
(single registration point — see src/models/__init__.py). Run in a subprocess so
other test modules' imports can't mask a missing registration."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_importing_models_package_registers_all_tables():
    code = (
        "import src.models; from src.models.base import Base; "
        "tables = set(Base.metadata.tables); "
        "required = {'pokemon', 'types', 'abilities', 'moves', 'pokemon_stats', "
        "'pokemon_types', 'type_effectiveness', 'api_resource', 'natures', 'machines'}; "
        "missing = required - tables; "
        "assert not missing, f'unregistered: {sorted(missing)}'; "
        "print('ok', len(tables))"
    )
    result = subprocess.run(  # noqa: S603 - fixed args, trusted interpreter
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0, result.stderr
