"""PokéAPI full-mirror DAG — one task per resource, wired from the registry."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

from src.ingestion.mirror import run_mirror
from src.ingestion.resources import RESOURCES

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    # Cap concurrent resource tasks so the global PokéAPI request rate stays
    # bounded (each task has its own client/rate-limiter). The pool is created by
    # the airflow-init service. Be a good PokéAPI citizen.
    "pool": "pokeapi_mirror",
}


def _mirror_resource(resource_name: str):
    """Mirror exactly one resource (DAG task ordering handles dependencies)."""
    run_mirror(only=[resource_name], expand_deps=False)


def _task_id(name: str) -> str:
    return f"mirror_{name.replace('-', '_')}"


with DAG(
    "pokeapi_mirror",
    default_args=default_args,
    description="Mirror all PokéAPI resources into the local database (generic engine)",
    # Weekly — the mirror is large (thousands of requests) and largely static.
    schedule="0 2 * * 0",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["pokemon", "mirror"],
) as dag:
    tasks = {
        spec.name: PythonOperator(
            task_id=_task_id(spec.name),
            python_callable=_mirror_resource,
            op_args=[spec.name],
        )
        for spec in RESOURCES
    }

    # Wire dependency edges: each resource runs after its FK parents.
    for spec in RESOURCES:
        for dep in spec.depends_on:
            tasks[dep] >> tasks[spec.name]
