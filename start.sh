#!/bin/bash
# Start script for the Pokémon Data Analytics Platform

# Set default environment (dev or prod)
ENV=${1:-dev}
VALID_ENVS=("dev" "prod")

# Validate environment argument
if [[ ! " ${VALID_ENVS[@]} " =~ " ${ENV} " ]]; then
    echo "Error: Invalid environment '$ENV'. Please use 'dev' or 'prod'."
    echo "Usage: $0 [dev|prod]"
    exit 1
fi

echo "Starting Pokémon Data Analytics Platform in $ENV environment..."

# Build and start the services
docker-compose -f docker/docker-compose.$ENV.yml up -d --build

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 10

# Initialize Airflow if needed
if ! docker-compose -f docker/docker-compose.$ENV.yml exec airflow-webserver airflow users list | grep -q "admin"; then
    echo "Initializing Airflow..."
    docker-compose -f docker/docker-compose.$ENV.yml exec airflow-webserver airflow db init
    docker-compose -f docker/docker-compose.$ENV.yml exec airflow-webserver airflow users create \
        --username admin \
        --firstname Admin \
        --lastname User \
        --role Admin \
        --email admin@example.com \
        --password admin
fi

# Check if services are running
if docker-compose -f docker/docker-compose.$ENV.yml ps | grep -q "Up"; then
    echo "Services are up and running!"
    
    # Print out access information
    echo ""
    echo "Access the platform at:"
    echo "- Airflow Dashboard: http://localhost:8080"
    if [ "$ENV" = "prod" ]; then
        echo "- Streamlit Dashboard: http://localhost:8501"
    fi
    echo ""
    echo "To run commands in the app container:"
    echo "docker-compose -f docker/docker-compose.$ENV.yml exec app python -m src.main [command]"
    echo ""
    echo "To view logs:"
    echo "docker-compose -f docker/docker-compose.$ENV.yml logs -f"
else
    echo "Error: Some services failed to start. Check the logs with:"
    echo "docker-compose -f docker/docker-compose.$ENV.yml logs -f"
    exit 1
fi