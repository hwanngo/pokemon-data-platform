"""Pokémon ETL DAG definition."""
import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion.pokemon_fetcher import PokemonFetcher
from src.ingestion.type_fetcher import TypeFetcher
from src.ingestion.ability_fetcher import AbilityFetcher
from src.transformation.pokemon_transformer import PokemonTransformer
from src.transformation.type_transformer import TypeTransformer
from src.transformation.ability_transformer import AbilityTransformer
from src.loading.db_loader import DatabaseLoader

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
}

def fetch_pokemon_data(**context):
    """Fetch Pokémon data from the API."""
    fetcher = PokemonFetcher()
    raw_data = fetcher.fetch_pokemon_batch(start_id=1, end_id=151)
    context['task_instance'].xcom_push(key='raw_pokemon_data', value=raw_data)

def transform_pokemon_data(**context):
    """Transform raw Pokémon data."""
    raw_data = context['task_instance'].xcom_pull(task_ids='fetch_pokemon_data', key='raw_pokemon_data')
    transformer = PokemonTransformer()
    transformed_data = transformer.transform_pokemon_batch(raw_data)
    context['task_instance'].xcom_push(key='transformed_pokemon_data', value=transformed_data)

def fetch_type_data(**context):
    """Fetch Type data from the API."""
    fetcher = TypeFetcher()
    raw_data = fetcher.fetch_all_types_with_effectiveness()
    context['task_instance'].xcom_push(key='raw_type_data', value=raw_data)

def transform_type_data(**context):
    """Transform raw Type data."""
    raw_data = context['task_instance'].xcom_pull(task_ids='fetch_type_data', key='raw_type_data')
    transformer = TypeTransformer()
    transformed_data = transformer.transform_type_batch(raw_data)
    context['task_instance'].xcom_push(key='transformed_type_data', value=transformed_data)

def fetch_ability_data(**context):
    """Fetch Ability data from the API."""
    fetcher = AbilityFetcher()
    raw_data = fetcher.fetch_all_abilities()
    context['task_instance'].xcom_push(key='raw_ability_data', value=raw_data)

def transform_ability_data(**context):
    """Transform raw Ability data."""
    raw_data = context['task_instance'].xcom_pull(task_ids='fetch_ability_data', key='raw_ability_data')
    transformer = AbilityTransformer()
    transformed_data = transformer.transform_ability_batch(raw_data)
    context['task_instance'].xcom_push(key='transformed_ability_data', value=transformed_data)

def load_data(**context):
    """Load transformed data into the database in the correct order."""
    transformed_type_data = context['task_instance'].xcom_pull(task_ids='transform_type_data', key='transformed_type_data')
    transformed_ability_data = context['task_instance'].xcom_pull(task_ids='transform_ability_data', key='transformed_ability_data')
    transformed_pokemon_data = context['task_instance'].xcom_pull(task_ids='transform_pokemon_data', key='transformed_pokemon_data')
    
    db_loader = DatabaseLoader()
    # Load in correct order: types -> abilities -> pokemon
    db_loader.load_all_type_data(transformed_type_data)
    db_loader.load_all_ability_data(transformed_ability_data)
    db_loader.load_all_pokemon_data(transformed_pokemon_data)

with DAG(
    'pokemon_etl',
    default_args=default_args,
    description='ETL pipeline for Pokémon data',
    schedule_interval='0 0 * * *',  # Daily at midnight
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['pokemon'],
) as dag:

    # Tasks
    fetch_types = PythonOperator(
        task_id='fetch_type_data',
        python_callable=fetch_type_data,
    )

    transform_types = PythonOperator(
        task_id='transform_type_data',
        python_callable=transform_type_data,
    )

    fetch_abilities = PythonOperator(
        task_id='fetch_ability_data',
        python_callable=fetch_ability_data,
    )

    transform_abilities = PythonOperator(
        task_id='transform_ability_data',
        python_callable=transform_ability_data,
    )

    fetch_pokemon = PythonOperator(
        task_id='fetch_pokemon_data',
        python_callable=fetch_pokemon_data,
    )

    transform_pokemon = PythonOperator(
        task_id='transform_pokemon_data',
        python_callable=transform_pokemon_data,
    )

    load_all = PythonOperator(
        task_id='load_data',
        python_callable=load_data,
    )

    # Define task dependencies in correct order
    # First types
    fetch_types >> transform_types
    # Then abilities
    transform_types >> fetch_abilities >> transform_abilities
    # Then pokemon
    transform_abilities >> fetch_pokemon >> transform_pokemon >> load_all