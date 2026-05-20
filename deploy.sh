#!/bin/bash
# Production deployment script for Longley-Rice RF Coverage Web Application

set -e

echo "=========================================="
echo "Longley-Rice RF Coverage App - Deployment"
echo "=========================================="

# Configuration
APP_NAME="rf-coverage-app"
DOCKER_COMPOSE_FILE="docker-compose.yml"
NGINX_CONF="nginx.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p dem_cache output logs ssl

# Set proper permissions
print_status "Setting permissions..."
chmod 755 dem_cache output logs
chmod 644 nginx.conf

# Build and start the application
print_status "Building and starting the application..."
docker-compose -f $DOCKER_COMPOSE_FILE up --build -d

# Wait for the application to start
print_status "Waiting for application to start..."
sleep 30

# Check if the application is running
print_status "Checking application health..."
if curl -f http://localhost:8000/api/health > /dev/null 2>&1; then
    print_status "Application is running successfully!"
    print_status "Web interface: http://localhost:8000"
    print_status "API documentation: http://localhost:8000/docs"
else
    print_error "Application failed to start. Checking logs..."
    docker-compose -f $DOCKER_COMPOSE_FILE logs
    exit 1
fi

# Show running containers
print_status "Running containers:"
docker-compose -f $DOCKER_COMPOSE_FILE ps

# Show useful commands
echo ""
print_status "Useful commands:"
echo "  View logs: docker-compose -f $DOCKER_COMPOSE_FILE logs -f"
echo "  Stop app: docker-compose -f $DOCKER_COMPOSE_FILE down"
echo "  Restart app: docker-compose -f $DOCKER_COMPOSE_FILE restart"
echo "  Update app: docker-compose -f $DOCKER_COMPOSE_FILE up --build -d"

echo ""
print_status "Deployment completed successfully!"
echo "=========================================="
