#!/bin/bash
# =============================================================================
# Build and Run RF Coverage Mapper Docker Container
# =============================================================================
# Usage:
#   ./build.sh          # Build and run
#   ./build.sh build    # Build only
#   ./build.sh run      # Run only (must have built first)
#   ./build.sh stop     # Stop container
#   ./build.sh clean    # Stop and remove all data
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SCRIPT_DIR"

case "${1:-all}" in
    build)
        echo "Building RF Coverage Mapper container..."
        docker-compose build
        echo "✓ Build complete"
        ;;
    run)
        echo "Starting RF Coverage Mapper..."
        docker-compose up -d
        echo "✓ Container started"
        echo "  Access at: http://localhost:8000"
        ;;
    stop)
        echo "Stopping RF Coverage Mapper..."
        docker-compose down
        echo "✓ Container stopped"
        ;;
    clean)
        echo "Stopping and removing all data..."
        docker-compose down -v
        echo "✓ Container and volumes removed"
        ;;
    logs)
        docker-compose logs -f
        ;;
    all|"")
        echo "Building and starting RF Coverage Mapper..."
        docker-compose up --build -d
        echo ""
        echo "============================================"
        echo "✓ RF Coverage Mapper is running!"
        echo "  Access at: http://localhost:8000"
        echo ""
        echo "  View logs:  ./build.sh logs"
        echo "  Stop:       ./build.sh stop"
        echo "============================================"
        ;;
    *)
        echo "Usage: $0 {build|run|stop|clean|logs}"
        exit 1
        ;;
esac



