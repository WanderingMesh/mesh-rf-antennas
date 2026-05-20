# =============================================================================
# Longley-Rice RF Coverage Mapper - Docker Container
# =============================================================================
# This Dockerfile builds a complete container with:
# - Python 3.11 runtime
# - SPLAT! RF propagation tool (compiled from source)
# - All Python dependencies
# - Pre-cached SRTM terrain data for Nevada region
# =============================================================================

FROM python:3.11-slim-bookworm

LABEL maintainer="RF Coverage Mapper"
LABEL description="Longley-Rice RF Coverage Analysis with SPLAT! backend"
LABEL version="1.0"

# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV GDAL_DATA=/usr/share/gdal
ENV PROJ_LIB=/usr/share/proj
ENV SPLAT_PATH=/app/splat_src/splat-1.4.2

WORKDIR /app

# =============================================================================
# SYSTEM DEPENDENCIES
# =============================================================================
# Install build tools and geospatial libraries needed for:
# - SPLAT! compilation (g++, make, bzip2)
# - GDAL/rasterio (libgdal-dev, gdal-bin)
# - Geospatial Python libs (libproj-dev, libgeos-dev)
# - Health checks (curl)
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools for SPLAT!
    g++ \
    gcc \
    make \
    bzip2 \
    libbz2-dev \
    # Geospatial libraries
    libgdal-dev \
    gdal-bin \
    libproj-dev \
    libgeos-dev \
    libspatialindex-dev \
    # For elevation library SRTM downloads
    unzip \
    wget \
    # Utilities
    curl \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# PYTHON DEPENDENCIES
# =============================================================================
# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python packages
# Note: Some packages need GDAL headers, so we install after system deps
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =============================================================================
# SPLAT! COMPILATION
# =============================================================================
# Copy SPLAT! source and compile
# SPLAT! is the core RF propagation engine using Longley-Rice ITM model
COPY splat_src/ ./splat_src/

# Compile SPLAT! (STANDARD version, not HD) and srtm2sdf utility
# CRITICAL: Must use std-parms.h NOT hd-parms.h for standard terrain files!
RUN cd /app/splat_src/splat-1.4.2 && \
    # Use standard parameters (1200x1200 terrain, not 3600x3600 HD)
    cp std-parms.h splat.h && \
    # Compile main SPLAT! binary (C++) - standard version
    g++ -Wall -O3 -ffast-math -fomit-frame-pointer -Wno-register \
        -o splat splat.cpp itwom3.0.cpp -lm -lbz2 && \
    # Compile srtm2sdf (C file with old K&R style - use gcc with legacy support)
    cd utils && \
    gcc -Wall -O3 -std=gnu89 -o srtm2sdf srtm2sdf.c -lm -lbz2 && \
    # Verify compilation
    echo "SPLAT! (standard) compilation complete:" && \
    ls -la /app/splat_src/splat-1.4.2/splat && \
    ls -la /app/splat_src/splat-1.4.2/utils/srtm2sdf

# =============================================================================
# APPLICATION CODE
# =============================================================================
# Copy application source code
COPY app.py config.py ./
COPY src/ ./src/
COPY static/ ./static/
COPY templates/ ./templates/

# =============================================================================
# RUNTIME SETUP
# =============================================================================
# Create necessary directories with proper permissions
RUN mkdir -p dem_cache output logs coverage_db splat_cache /root/.cache/elevation

# Copy pre-cached terrain data for Nevada region
# These SDF files allow calculations without network access
COPY splat_test/*.sdf ./splat_test/
COPY splat_test/*.sdf ./splat_cache/

# Set cache permissions
RUN chmod -R 777 dem_cache splat_cache /root/.cache

# Set permissions
RUN chmod +x /app/splat_src/splat-1.4.2/splat && \
    chmod +x /app/splat_src/splat-1.4.2/utils/srtm2sdf

# Expose the application port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# =============================================================================
# STARTUP
# =============================================================================
# Run the FastAPI application with uvicorn
CMD ["python", "app.py"]

