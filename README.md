# Pokémon Data Analytics Platform

A comprehensive data analytics platform that collects, processes, and analyzes Pokémon data from PokéAPI, featuring real-time visualizations and automated data pipelines.

## Features

- 🔄 Automated ETL pipeline with Apache Airflow
- 📊 Interactive Streamlit dashboard with:
  - Top Pokémon analysis by stats
  - Type distribution visualization
  - Type effectiveness matrix
  - Individual Pokémon analysis
- 🔍 FastAPI backend for data access
- 🐘 PostgreSQL database with efficient schema
- 🐋 Docker-based deployment
- ⚡ Rate-limited API fetching with caching

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.10+

### Setup

1. Clone the repository
2. Start all services:
   ```bash
   docker-compose -f docker/docker-compose.dev.yml up -d
   ```
3. Access the services:
   - Dashboard: http://localhost:8000
   - Airflow UI: http://localhost:8080 (login: admin/admin)

## Project Structure

```
pokemon-data-platform/
├── src/
│   ├── analytics/      # Dashboard and data analysis
│   ├── ingestion/      # PokéAPI data fetching
│   ├── transformation/ # Data transformation
│   ├── loading/        # Database operations
│   ├── models/         # SQLAlchemy models
│   └── dags/           # Airflow DAG definitions
├── database/           # DB migrations and schema
├── docker/             # Docker configuration
└── requirements/       # Python dependencies
```

## Data Pipeline

The ETL pipeline runs daily and includes:

1. **Extract**: Fetches data from PokéAPI
   - Pokémon details
   - Type information
   - Abilities
   
2. **Transform**: Processes raw data
   - Normalizes data structures
   - Calculates derived statistics
   - Generates type effectiveness matrices

3. **Load**: Updates PostgreSQL database
   - Maintains data consistency
   - Handles incremental updates
   - Preserves historical data

4. **Analyze**: Provides insights through:
   - Base stat distributions
   - Type effectiveness analysis
   - Move coverage metrics
   - Generation-based comparisons

## Configuration

Key configuration options in `docker-compose.dev.yml`:
- Database credentials
- API rate limits
- Cache settings
- Resource limits

## Development

1. Install dev dependencies:
   ```bash
   pip install -r requirements/dev.txt
   ```

2. Run tests:
   ```bash
   python -m pytest tests/
   ```

## Performance Considerations

- API requests are cached to minimize external calls
- Database queries are optimized with proper indexing
- Docker containers have defined resource limits
- Airflow tasks use efficient parallel execution

## License

MIT