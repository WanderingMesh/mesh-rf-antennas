#!/usr/bin/env python3
"""
Longley-Rice RF Coverage Web Application

A production-ready web application for RF coverage mapping using the Longley-Rice
propagation model, following SPLAT! methodology for accuracy and compatibility.

Features:
- Single site coverage calculation
- Multi-site coverage with node visibility options
- Interactive web interface with Leaflet maps
- SPLAT! compatible Longley-Rice propagation modeling
- Terrain-aware coverage analysis using SRTM data

Usage:
    python app.py

API Endpoints:
- GET / - Main web interface
- POST /api/coverage/single - Generate single site coverage
- POST /api/coverage/multi - Generate multi-site coverage
- GET /api/coverage/{coverage_id} - Get coverage data
- GET /api/coverage/{coverage_id}/map - Get coverage map image
"""

import os
import sys
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import asyncio
import aiofiles
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import secrets
import uvicorn
import pandas as pd
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from src.coverage_calculator import CoverageCalculator
from src.export_service import export_kmz, export_geotiff
from config import get_config, validate_config

# ============================================================================
# DATA MODELS
# ============================================================================

class SingleSiteRequest(BaseModel):
    """Request model for single site coverage calculation."""
    site_name: str = Field(..., description="Name of the site")
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    elev_m: float = Field(..., ge=0, le=10000, description="Elevation in meters")
    frequency_mhz: float = Field(900.0, ge=100, le=6000, description="Frequency in MHz")
    tx_power_dbm: float = Field(30.0, ge=-50, le=50, description="Transmitter power in dBm")
    antenna_gain_dbi: float = Field(0.0, ge=-20, le=30, description="Antenna gain in dBi")
    antenna_type: str = Field("omnidirectional", description="Antenna type (omnidirectional, yagi_3el, yagi_5el, yagi_11el)")
    antenna_azimuth: float = Field(0.0, ge=0, le=360, description="Antenna pointing direction in degrees (0=North, 90=East)")
    antenna_tilt: float = Field(0.0, ge=-10, le=10, description="Antenna tilt in degrees (positive=down, negative=up)")
    antenna_tilt_azimuth: float = Field(0.0, ge=0, le=360, description="Compass direction the antenna tilts toward (0=North, 90=East)")
    rx_sensitivity_dbm: float = Field(-100.0, ge=-150, le=-50, description="Receiver sensitivity in dBm")
    analysis_radius_km: float = Field(50.0, ge=1, le=200, description="Analysis radius in kilometers")
    climate_zone: str = Field("desert", description="ITU climate zone for propagation model")
    ground_type: str = Field("desert", description="Ground type affecting dielectric/conductivity")
    fraction_of_time: float = Field(0.50, ge=0.01, le=0.99, description="Fraction of time reliability (lower = more optimistic)")

class MultiSiteRequest(BaseModel):
    """Request model for multi-site coverage calculation."""
    sites: List[Dict[str, float]] = Field(..., description="List of sites with lat, lon, elev")
    show_nodes: bool = Field(True, description="Whether to show node locations")
    frequency_mhz: float = Field(900.0, ge=100, le=6000, description="Frequency in MHz")
    tx_power_dbm: float = Field(30.0, ge=-50, le=50, description="Transmitter power in dBm")
    antenna_gain_dbi: float = Field(0.0, ge=-20, le=30, description="Antenna gain in dBi")
    antenna_type: str = Field("omnidirectional", description="Antenna type (omnidirectional, yagi_3el, yagi_5el, yagi_11el)")
    antenna_azimuth: float = Field(0.0, ge=0, le=360, description="Antenna pointing direction in degrees (0=North, 90=East)")
    antenna_tilt: float = Field(0.0, ge=-10, le=10, description="Antenna tilt in degrees (positive=down, negative=up)")
    antenna_tilt_azimuth: float = Field(0.0, ge=0, le=360, description="Compass direction the antenna tilts toward (0=North, 90=East)")
    rx_sensitivity_dbm: float = Field(-100.0, ge=-150, le=-50, description="Receiver sensitivity in dBm")
    analysis_radius_km: float = Field(50.0, ge=1, le=200, description="Analysis radius in kilometers")
    climate_zone: str = Field("desert", description="ITU climate zone for propagation model")
    ground_type: str = Field("desert", description="Ground type affecting dielectric/conductivity")
    fraction_of_time: float = Field(0.50, ge=0.01, le=0.99, description="Fraction of time reliability (lower = more optimistic)")

class CoverageResponse(BaseModel):
    """Response model for coverage calculations."""
    coverage_id: str
    status: str
    message: str
    coverage_data: Optional[Dict] = None
    statistics: Optional[Dict] = None
    created_at: str

# ============================================================================
# WEB APPLICATION
# ============================================================================

# Initialize FastAPI app
app = FastAPI(
    title="Longley-Rice RF Coverage Web Application",
    description="Production-ready RF coverage mapping using SPLAT! compatible Longley-Rice model",
    version="0.20.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Global configuration and storage
config = get_config('default')
coverage_storage = {}  # In-memory cache

# Security: Admin API key for cache management
# In production, load this from environment variable or secure config
ADMIN_API_KEY = os.getenv('ADMIN_API_KEY', secrets.token_urlsafe(32))
print(f"\n{'='*80}")
print(f"ADMIN API KEY (save this for cache management): {ADMIN_API_KEY}")
print(f"{'='*80}\n")

security = HTTPBearer()

def verify_admin_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin API key for protected endpoints."""
    if credentials.credentials != ADMIN_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing admin API key"
        )
    return credentials.credentials

# Persistent storage using SQLite
import sqlite3
from pathlib import Path as FilePath

# Create database directory
db_dir = FilePath("coverage_db")
db_dir.mkdir(exist_ok=True)
db_path = db_dir / "coverage_cache.db"

def init_db():
    """Initialize the coverage cache database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS site_coverage (
            site_key TEXT PRIMARY KEY,
            site_name TEXT,
            lat REAL,
            lon REAL,
            elev_m REAL,
            frequency_mhz REAL,
            tx_power_dbm REAL,
            coverage_data BLOB,
            created_at TEXT,
            last_accessed TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

def get_site_key(lat: float, lon: float, elev_m: float, frequency_mhz: float, tx_power_dbm: float, 
                 antenna_gain_dbi: float = 0.0, antenna_type: str = "omnidirectional", antenna_azimuth: float = 0.0,
                 antenna_tilt: float = 0.0, antenna_tilt_azimuth: float = 0.0,
                 rx_sensitivity_dbm: float = -100.0, analysis_radius_km: float = 50.0,
                 climate_zone: str = "desert", ground_type: str = "desert",
                 fraction_of_time: float = 0.50) -> str:
    """Generate unique key for a site configuration (rounded to avoid float precision issues)."""
    return (f"{lat:.6f}_{lon:.6f}_{elev_m:.1f}_{frequency_mhz:.1f}_{tx_power_dbm:.1f}_"
            f"{antenna_gain_dbi:.1f}_{antenna_type}_{antenna_azimuth:.1f}_{antenna_tilt:.1f}_"
            f"{antenna_tilt_azimuth:.1f}_{rx_sensitivity_dbm:.0f}_{analysis_radius_km:.0f}_"
            f"{climate_zone}_{ground_type}_{fraction_of_time:.2f}")

def load_cached_coverage(site_key: str) -> Optional[Dict]:
    """Load coverage data from database if it exists."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT coverage_data, created_at FROM site_coverage WHERE site_key = ?
        ''', (site_key,))
        result = cursor.fetchone()
        
        if result:
            # Update last accessed time
            cursor.execute('''
                UPDATE site_coverage SET last_accessed = ? WHERE site_key = ?
            ''', (datetime.now().isoformat(), site_key))
            conn.commit()
            
            # Deserialize coverage data
            import pickle
            coverage_data = pickle.loads(result[0])
            conn.close()
            return coverage_data
        
        conn.close()
        return None
    except Exception as e:
        print(f"Error loading cached coverage: {e}")
        return None

def save_coverage_to_db(site_key: str, site_name: str, lat: float, lon: float, 
                        elev_m: float, frequency_mhz: float, tx_power_dbm: float, antenna_gain_dbi: float,
                        coverage_data: Dict):
    """Save coverage data to database for future reuse."""
    try:
        import pickle
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Serialize coverage data
        coverage_blob = pickle.dumps(coverage_data)
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO site_coverage 
            (site_key, site_name, lat, lon, elev_m, frequency_mhz, tx_power_dbm, 
             coverage_data, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (site_key, site_name, lat, lon, elev_m, frequency_mhz, tx_power_dbm,
              coverage_blob, now, now))
        
        conn.commit()
        conn.close()
        print(f"Saved coverage to database: {site_key}")
    except Exception as e:
        print(f"Error saving coverage to database: {e}")

# Validate configuration
if not validate_config(config):
    print("Configuration validation failed!")
    sys.exit(1)

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main web interface."""
    return templates.TemplateResponse(request, "index.html")

@app.post("/api/coverage/single", response_model=CoverageResponse)
async def calculate_single_site_coverage(request: SingleSiteRequest):
    """
    Submit coverage calculation request.
    Returns immediately with 'processing' status.
    Calculation runs in background.
    """
    try:
        # Generate unique coverage ID
        coverage_id = str(uuid.uuid4())
        
        # Store initial status
        coverage_storage[coverage_id] = {
            'status': 'processing',
            'created_at': datetime.now().isoformat(),
            'type': 'single_site',
            'request': request.dict()
        }
        
        # Start background calculation
        asyncio.create_task(
            _calculate_coverage_background(coverage_id, request)
        )
        
        return CoverageResponse(
            coverage_id=coverage_id,
            status="processing",
            message="Coverage calculation started. Poll /api/coverage/{coverage_id}/status for updates.",
            coverage_data=None,
            statistics=None,
            created_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting coverage calculation: {str(e)}")


async def _calculate_coverage_background(coverage_id: str, request: SingleSiteRequest):
    """Background task to calculate coverage with proper terrain analysis and progress updates."""
    try:
        # Generate site key for caching
        site_key = get_site_key(request.lat, request.lon, request.elev_m, 
                               request.frequency_mhz, request.tx_power_dbm, request.antenna_gain_dbi,
                               request.antenna_type, request.antenna_azimuth,
                               request.antenna_tilt, request.antenna_tilt_azimuth,
                               request.rx_sensitivity_dbm, request.analysis_radius_km,
                               request.climate_zone, request.ground_type,
                               request.fraction_of_time)
        
        # Check if we have cached coverage for this exact site
        cached_coverage = load_cached_coverage(site_key)
        
        if cached_coverage:
            print(f"Using cached coverage for {site_key}")
            coverage_storage[coverage_id].update({
                'status': 'complete',
                'coverage_data': cached_coverage,
                'progress': 100.0,
                'progress_message': 'Loaded from cache',
                'completed_at': datetime.now().isoformat(),
                'from_cache': True
            })
            return
        
        # Not cached - calculate it
        coverage_storage[coverage_id].update({
            'progress': 5.0,
            'progress_message': 'Initializing calculation...'
        })
        
        calc_config = config.copy()
        calc_config['rf'].update({
            'frequency_mhz': request.frequency_mhz,
            'tx_power_dbm': request.tx_power_dbm,
            'antenna_gain_dbi': request.antenna_gain_dbi,
            'antenna_type': request.antenna_type,
            'antenna_azimuth': request.antenna_azimuth,
            'antenna_tilt': request.antenna_tilt,
            'antenna_tilt_azimuth': request.antenna_tilt_azimuth,
            'rx_sensitivity_dbm': request.rx_sensitivity_dbm,
            'climate_zone': request.climate_zone,
            'ground_type': request.ground_type,
            'fraction_of_time': request.fraction_of_time
        })
        calc_config['dem'].update({
            'analysis_radius_km': request.analysis_radius_km
        })
        
        calculator = CoverageCalculator(calc_config)
        
        def progress_callback(progress: float, message: str):
            coverage_storage[coverage_id].update({
                'progress': progress,
                'progress_message': message
            })
        
        coverage_data = calculator.calculate_single_site_coverage(
            site_name=request.site_name,
            lat=request.lat,
            lon=request.lon,
            elev_m=request.elev_m,
            progress_callback=progress_callback
        )
        
        # Save to database for future reuse
        save_coverage_to_db(site_key, request.site_name, request.lat, request.lon,
                           request.elev_m, request.frequency_mhz, request.tx_power_dbm, request.antenna_gain_dbi,
                           coverage_data)
        
        # Update storage with results
        coverage_storage[coverage_id].update({
            'status': 'complete',
            'coverage_data': coverage_data,
            'progress': 100.0,
            'progress_message': 'Complete',
            'completed_at': datetime.now().isoformat(),
            'from_cache': False
        })
        
    except Exception as e:
        # Update storage with error
        coverage_storage[coverage_id].update({
            'status': 'error',
            'error': str(e),
            'completed_at': datetime.now().isoformat()
        })

@app.post("/api/coverage/multi", response_model=CoverageResponse)
async def calculate_multi_site_coverage(request: MultiSiteRequest):
    """Calculate coverage for multiple sites."""
    try:
        # Generate unique coverage ID
        coverage_id = str(uuid.uuid4())
        
        # Convert sites to DataFrame
        sites_df = pd.DataFrame(request.sites)
        
        # Validate required columns
        required_columns = ['name', 'lat', 'lon', 'elev']
        if not all(col in sites_df.columns for col in required_columns):
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required columns. Need: {required_columns}"
            )
        
        calc_config = config.copy()
        calc_config['rf'].update({
            'frequency_mhz': request.frequency_mhz,
            'tx_power_dbm': request.tx_power_dbm,
            'antenna_gain_dbi': request.antenna_gain_dbi,
            'antenna_type': request.antenna_type,
            'antenna_azimuth': request.antenna_azimuth,
            'antenna_tilt': request.antenna_tilt,
            'antenna_tilt_azimuth': request.antenna_tilt_azimuth,
            'rx_sensitivity_dbm': request.rx_sensitivity_dbm,
            'climate_zone': request.climate_zone,
            'ground_type': request.ground_type,
            'fraction_of_time': request.fraction_of_time
        })
        calc_config['dem'].update({
            'analysis_radius_km': request.analysis_radius_km
        })
        
        calculator = CoverageCalculator(calc_config)
        
        coverage_data = calculator.calculate_multi_site_coverage(
            sites_df=sites_df,
            show_nodes=request.show_nodes
        )
        
        # Store coverage data
        coverage_storage[coverage_id] = {
            'coverage_data': coverage_data,
            'created_at': datetime.now().isoformat(),
            'type': 'multi_site'
        }
        
        return CoverageResponse(
            coverage_id=coverage_id,
            status="success",
            message="Multi-site coverage calculated successfully",
            coverage_data=None,  # Don't return full coverage data - it has NumPy arrays
            statistics=coverage_data.get('statistics'),
            created_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating coverage: {str(e)}")

@app.get("/api/coverage/{coverage_id}/status")
async def get_coverage_status(coverage_id: str):
    """Get current status and progress of coverage calculation."""
    if coverage_id not in coverage_storage:
        raise HTTPException(status_code=404, detail="Coverage data not found")
    
    stored_data = coverage_storage[coverage_id]
    
    return {
        'coverage_id': coverage_id,
        'status': stored_data.get('status', 'unknown'),
        'progress': stored_data.get('progress', 0.0),
        'progress_message': stored_data.get('progress_message', ''),
        'created_at': stored_data.get('created_at'),
        'completed_at': stored_data.get('completed_at'),
        'error': stored_data.get('error')
    }


@app.get("/api/coverage/{coverage_id}")
async def get_coverage_data(coverage_id: str):
    """Get coverage data by ID with proper JSON serialization."""
    if coverage_id not in coverage_storage:
        raise HTTPException(status_code=404, detail="Coverage data not found")
    
    stored_data = coverage_storage[coverage_id]
    
    # Check if still processing
    if stored_data.get('status') == 'processing':
        return {
            'status': 'processing',
            'progress': stored_data.get('progress', 0.0),
            'progress_message': stored_data.get('progress_message', '')
        }
    
    # Check if error
    if stored_data.get('status') == 'error':
        return {
            'status': 'error',
            'error': stored_data.get('error')
        }
    
    coverage_data = stored_data['coverage_data']
    
    # Convert numpy arrays to lists for JSON serialization
    serializable_data = {
        'status': 'complete',
        'coverage_mask': coverage_data['coverage_mask'].tolist() if isinstance(coverage_data['coverage_mask'], np.ndarray) else coverage_data['coverage_mask'],
        'signal_strength': coverage_data['signal_strength'].tolist() if isinstance(coverage_data['signal_strength'], np.ndarray) else coverage_data['signal_strength'],
        'tx_lat': coverage_data.get('tx_lat'),
        'tx_lon': coverage_data.get('tx_lon'),
        'tx_elev_m': coverage_data.get('tx_elev_m'),
        'frequency_mhz': coverage_data.get('frequency_mhz'),
        'tx_power_dbm': coverage_data.get('tx_power_dbm'),
        'antenna_gain_dbi': coverage_data.get('antenna_gain_dbi'),
        'antenna_type': coverage_data.get('antenna_type'),
        'antenna_azimuth': coverage_data.get('antenna_azimuth'),
        'antenna_tilt': coverage_data.get('antenna_tilt'),
        'antenna_tilt_azimuth': coverage_data.get('antenna_tilt_azimuth'),
        'site_name': coverage_data.get('site_name'),
        'dem_bounds': coverage_data.get('dem_bounds'),
        'dem_transform': coverage_data.get('dem_transform'),
        'statistics': coverage_data.get('statistics'),
        'created_at': stored_data.get('created_at'),
        'type': stored_data.get('type')
    }
    
    return serializable_data

@app.get("/api/coverage/{coverage_id}/map")
async def get_coverage_map(coverage_id: str, format: str = "png"):
    """Get coverage map image."""
    if coverage_id not in coverage_storage:
        raise HTTPException(status_code=404, detail="Coverage data not found")
    
    coverage_data = coverage_storage[coverage_id]['coverage_data']
    
    # Generate map image
    map_path = await generate_coverage_map_image(coverage_data, coverage_id, format)
    
    return FileResponse(map_path, media_type=f"image/{format}")

@app.get("/api/coverage/{coverage_id}/export/kmz")
async def export_coverage_kmz(coverage_id: str):
    """Export coverage layer as a KMZ file (KML + PNG overlay) for Google Earth."""
    if coverage_id not in coverage_storage:
        raise HTTPException(status_code=404, detail="Coverage data not found")
    
    stored = coverage_storage[coverage_id]
    if stored.get('status') != 'complete':
        raise HTTPException(status_code=400, detail="Coverage calculation not complete")
    
    coverage_data = stored['coverage_data']
    site_name = coverage_data.get('site_name', 'Coverage')
    
    try:
        kmz_bytes = export_kmz(coverage_data, site_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KMZ export failed: {str(e)}")
    
    safe_name = site_name.replace(' ', '_').replace('/', '_')
    return _binary_response(kmz_bytes, f'{safe_name}_coverage.kmz', 'application/vnd.google-earth.kmz')

@app.get("/api/coverage/{coverage_id}/export/geotiff")
async def export_coverage_geotiff(coverage_id: str):
    """Export coverage layer as a GeoTIFF with signal strength in dBm."""
    if coverage_id not in coverage_storage:
        raise HTTPException(status_code=404, detail="Coverage data not found")
    
    stored = coverage_storage[coverage_id]
    if stored.get('status') != 'complete':
        raise HTTPException(status_code=400, detail="Coverage calculation not complete")
    
    coverage_data = stored['coverage_data']
    site_name = coverage_data.get('site_name', 'Coverage')
    
    try:
        tiff_bytes = export_geotiff(coverage_data, site_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GeoTIFF export failed: {str(e)}")
    
    safe_name = site_name.replace(' ', '_').replace('/', '_')
    return _binary_response(tiff_bytes, f'{safe_name}_coverage.tif', 'image/tiff')


def _binary_response(data: bytes, filename: str, media_type: str):
    """Return binary data as a downloadable file response."""
    from starlette.responses import Response
    return Response(
        content=data,
        media_type=media_type,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.post("/api/coverage/upload")
async def upload_sites_file(file: UploadFile = File(...)):
    """Upload CSV file with sites data."""
    try:
        # Read uploaded file
        content = await file.read()
        
        # Parse CSV
        import io
        df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        
        # Validate required columns
        required_columns = ['name', 'lat', 'lon', 'elev']
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns. Need: {required_columns}"
            )
        
        # Convert to list of dictionaries
        sites = df[required_columns].to_dict('records')
        
        return {
            "status": "success",
            "message": f"Successfully uploaded {len(sites)} sites",
            "sites": sites
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@app.get("/api/config")
async def get_configuration():
    """Get current configuration."""
    return config

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/cache/list")
async def list_cached_sites(admin_key: str = Depends(verify_admin_key)):
    """
    List all cached coverage calculations.
    
    Requires admin API key in Authorization header:
    Authorization: Bearer {ADMIN_API_KEY}
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT site_key, site_name, lat, lon, elev_m, frequency_mhz, 
                   tx_power_dbm, created_at, last_accessed 
            FROM site_coverage 
            ORDER BY last_accessed DESC
        ''')
        results = cursor.fetchall()
        conn.close()
        
        sites = []
        for row in results:
            sites.append({
                'site_key': row[0],
                'site_name': row[1],
                'lat': row[2],
                'lon': row[3],
                'elev_m': row[4],
                'frequency_mhz': row[5],
                'tx_power_dbm': row[6],
                'created_at': row[7],
                'last_accessed': row[8]
            })
        
        return {
            'status': 'success',
            'count': len(sites),
            'sites': sites
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing cached sites: {str(e)}")

@app.delete("/api/cache/{site_key}")
async def delete_cached_site(site_key: str, admin_key: str = Depends(verify_admin_key)):
    """
    Delete a specific cached site.
    
    Requires admin API key in Authorization header:
    Authorization: Bearer {ADMIN_API_KEY}
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM site_coverage WHERE site_key = ?', (site_key,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Site not found in cache")
        
        return {
            'status': 'success',
            'message': f'Deleted site {site_key}',
            'deleted': deleted
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting cached site: {str(e)}")

@app.delete("/api/cache/clear")
async def clear_all_cache(admin_key: str = Depends(verify_admin_key)):
    """
    Clear all cached coverage data.
    
    Requires admin API key in Authorization header:
    Authorization: Bearer {ADMIN_API_KEY}
    
    WARNING: This deletes ALL cached coverage calculations!
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM site_coverage')
        count = cursor.fetchone()[0]
        cursor.execute('DELETE FROM site_coverage')
        conn.commit()
        conn.close()
        
        return {
            'status': 'success',
            'message': f'Cleared {count} cached sites',
            'deleted': count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

async def generate_coverage_map_image(coverage_data: Dict, coverage_id: str, format: str = "png") -> str:
    """Generate coverage map image."""
    try:
        # Create output directory
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        # Generate map image
        fig, ax = plt.subplots(figsize=(12, 10))
        
        if 'coverage_mask' in coverage_data:
            # Single site coverage
            coverage_mask = coverage_data['coverage_mask']
            signal_strength = coverage_data['signal_strength']
            
            # Create coverage visualization
            im = ax.imshow(signal_strength, cmap='viridis', alpha=0.7)
            
            # Add transmitter location
            tx_lat = coverage_data['tx_lat']
            tx_lon = coverage_data['tx_lon']
            # Convert to pixel coordinates (simplified)
            ax.plot(tx_lon, tx_lat, 'ro', markersize=10, label='Transmitter')
            
        elif 'site_coverage_data' in coverage_data:
            # Multi-site coverage
            combined_mask = coverage_data['coverage_mask']
            combined_signal = coverage_data['signal_strength']
            
            # Create combined coverage visualization
            im = ax.imshow(combined_signal, cmap='viridis', alpha=0.7)
            
            # Add node locations if requested
            if coverage_data.get('show_nodes', True) and 'node_locations' in coverage_data:
                for node in coverage_data['node_locations']:
                    ax.plot(node['lon'], node['lat'], 'ro', markersize=8)
        
        # Add colorbar
        plt.colorbar(im, ax=ax, label='Signal Strength (dBm)')
        
        # Set labels and title
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_title(f'RF Coverage Map - {coverage_id[:8]}')
        
        # Save image
        map_path = output_dir / f"coverage_map_{coverage_id}.{format}"
        plt.savefig(map_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return str(map_path)
        
    except Exception as e:
        print(f"Error generating map image: {e}")
        # Return a placeholder image
        placeholder_path = output_dir / f"placeholder.{format}"
        if not placeholder_path.exists():
            # Create a simple placeholder
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, 'Coverage Map\n(Error generating image)', 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            plt.savefig(placeholder_path, dpi=150, bbox_inches='tight')
            plt.close()
        return str(placeholder_path)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Run the web application."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Longley-Rice RF Coverage Web Application')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8001, help='Port to bind to')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    parser.add_argument('--config', default='default', choices=['default', 'development', 'production'],
                       help='Configuration type')
    
    args = parser.parse_args()
    
    # Load configuration
    global config
    config = get_config(args.config)
    
    print("="*80)
    print("LONGLEY-RICE RF COVERAGE WEB APPLICATION")
    print("="*80)
    print(f"Configuration: {args.config}")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Reload: {args.reload}")
    print("="*80)
    print("Starting server...")
    print("Press Ctrl+C to stop")
    print("="*80)
    
    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )

if __name__ == "__main__":
    main()
