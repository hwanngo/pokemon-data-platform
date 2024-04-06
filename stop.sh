#!/bin/bash

echo "Stopping Pokémon Data Platform services..."

# Stop Docker containers
echo "Stopping Docker containers..."
docker-compose -f docker/docker-compose.dev.yml down

# Kill any remaining Python processes (optional)
echo "Checking for any remaining Python processes..."
pkill -f "python src/main.py" || true

echo "All services stopped successfully!"