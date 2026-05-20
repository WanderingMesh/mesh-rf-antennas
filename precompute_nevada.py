#!/usr/bin/env python3
"""
Pre-compute terrain viewshed data for Nevada.

This script generates a database of line-of-sight and terrain blocking
information for a grid of points across Nevada. This allows real-time
RF coverage calculations with realistic terrain effects.

Usage:
    python precompute_nevada.py --resolution 5km --output nevada_viewshed.db
"""

import numpy as np
import sqlite3
import argparse
from pathlib import Path
import pickle
from tqdm import tqdm
import rasterio

# Nevada bounds
NEVADA_BOUNDS = {
    'west': -120.0,
    'east': -114.0,
    'south': 35.0,
    'north': 42.0
}

def create_viewshed_database(output_path: str):
    """Create SQLite database for viewshed data."""
    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()
    
    # Viewshed table: stores which directions are blocked from each grid point
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS viewshed (
            grid_lat REAL,
            grid_lon REAL,
            elevation REAL,
            azimuth INTEGER,
            max_distance_km REAL,
            blocking_data BLOB,
            PRIMARY KEY (grid_lat, grid_lon, azimuth)
        )
    ''')
    
    # Grid points table: stores elevation and terrain info for each grid point
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grid_points (
            lat REAL,
            lon REAL,
            elevation REAL,
            terrain_roughness REAL,
            PRIMARY KEY (lat, lon)
        )
    ''')
    
    # Create indices for fast lookup
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_viewshed_location ON viewshed(grid_lat, grid_lon)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_grid_location ON grid_points(lat, lon)')
    
    conn.commit()
    return conn

def download_nevada_dem():
    """
    Download DEM data for entire Nevada using our existing DEM handler.
    
    This is more reliable than using elevation.clip() directly for large areas.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'src'))
    
    from dem_handler import DEMHandler
    
    print("Downloading DEM data for Nevada using DEMHandler...")
    
    # Create DEM handler
    dem_handler = DEMHandler(cache_dir='dem_cache', resolution=90)
    
    # Download DEM for Nevada bounds
    bounds = (NEVADA_BOUNDS['west'], NEVADA_BOUNDS['south'], 
              NEVADA_BOUNDS['east'], NEVADA_BOUNDS['north'])
    
    print(f"Bounds: {bounds}")
    print("This will download DEM data in chunks...")
    
    dem_data, dem_transform = dem_handler.get_dem_data(bounds)
    
    print(f"✓ DEM data loaded: {dem_data.shape}")
    print(f"  Elevation range: {np.min(dem_data):.0f}m - {np.max(dem_data):.0f}m")
    
    # Save to a single file for the pre-computation
    output_file = Path('nevada_dem.tif').absolute()
    
    import rasterio
    from rasterio.transform import from_bounds
    
    # Create transform for the full Nevada extent
    transform = from_bounds(
        bounds[0], bounds[1], bounds[2], bounds[3],
        dem_data.shape[1], dem_data.shape[0]
    )
    
    # Write to file
    with rasterio.open(
        output_file,
        'w',
        driver='GTiff',
        height=dem_data.shape[0],
        width=dem_data.shape[1],
        count=1,
        dtype=dem_data.dtype,
        crs='EPSG:4326',
        transform=transform,
        compress='deflate'
    ) as dst:
        dst.write(dem_data, 1)
    
    print(f"✓ DEM data saved to: {output_file}")
    print(f"  File size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
    
    return str(output_file)

def calculate_viewshed_for_point(dem_data, dem_transform, lat, lon, elevation, num_azimuths=72):
    """
    Calculate viewshed for a single point.
    
    Returns dict of azimuth -> blocking profile
    """
    from src.splat_longley_rice import _latlon_to_pixel
    
    # Get pixel coordinates
    row, col = _latlon_to_pixel(lat, lon, dem_transform)
    
    if row < 0 or row >= dem_data.shape[0] or col < 0 or col >= dem_data.shape[1]:
        return {}
    
    viewshed_data = {}
    
    # For each azimuth, calculate terrain shadow profile
    for az_idx in range(num_azimuths):
        azimuth = (az_idx * 360.0) / num_azimuths
        azimuth_rad = np.radians(azimuth)
        
        dx = np.sin(azimuth_rad)
        dy = np.cos(azimuth_rad)
        
        # Track elevation angles along this ray
        max_elev_angle = -90.0
        blocking_profile = []
        
        max_steps = 500  # ~45km at 90m resolution
        
        for step in range(1, max_steps, 5):
            r = int(row + step * dy)
            c = int(col + step * dx)
            
            if r < 0 or r >= dem_data.shape[0] or c < 0 or c >= dem_data.shape[1]:
                break
            
            terrain_h = dem_data[r, c]
            dist_m = step * 90.0
            elev_angle = np.degrees(np.arctan2(terrain_h - elevation, dist_m))
            
            # Record blocking points
            if elev_angle > max_elev_angle:
                blocking_profile.append({
                    'distance_km': dist_m / 1000.0,
                    'elevation_angle': elev_angle,
                    'terrain_height': float(terrain_h)
                })
                max_elev_angle = elev_angle
        
        viewshed_data[int(azimuth)] = blocking_profile
    
    return viewshed_data

def precompute_nevada_grid(conn, dem_file, grid_spacing_km=5.0):
    """
    Pre-compute viewshed for a grid of points across Nevada.
    
    Args:
        conn: Database connection
        dem_file: Path to Nevada DEM file
        grid_spacing_km: Spacing between grid points in km
    """
    print(f"Pre-computing viewshed grid with {grid_spacing_km}km spacing...")
    
    # Load DEM
    with rasterio.open(dem_file) as src:
        dem_data = src.read(1)
        dem_transform = src.transform
    
    # Create grid of points across Nevada
    lat_step = grid_spacing_km / 111.0  # ~111km per degree latitude
    lon_step = grid_spacing_km / (111.0 * np.cos(np.radians(38.5)))  # Adjust for latitude
    
    lats = np.arange(NEVADA_BOUNDS['south'], NEVADA_BOUNDS['north'], lat_step)
    lons = np.arange(NEVADA_BOUNDS['west'], NEVADA_BOUNDS['east'], lon_step)
    
    total_points = len(lats) * len(lons)
    print(f"Processing {total_points} grid points...")
    
    cursor = conn.cursor()
    
    with tqdm(total=total_points) as pbar:
        for lat in lats:
            for lon in lons:
                # Get elevation at this point
                from src.splat_longley_rice import _latlon_to_pixel
                row, col = _latlon_to_pixel(lat, lon, dem_transform)
                
                if row < 0 or row >= dem_data.shape[0] or col < 0 or col >= dem_data.shape[1]:
                    pbar.update(1)
                    continue
                
                elevation = float(dem_data[row, col])
                
                # Calculate terrain roughness (std dev of nearby elevations)
                r_min = max(0, row - 10)
                r_max = min(dem_data.shape[0], row + 11)
                c_min = max(0, col - 10)
                c_max = min(dem_data.shape[1], col + 11)
                
                terrain_patch = dem_data[r_min:r_max, c_min:c_max]
                roughness = float(np.std(terrain_patch))
                
                # Store grid point
                cursor.execute('''
                    INSERT OR REPLACE INTO grid_points (lat, lon, elevation, terrain_roughness)
                    VALUES (?, ?, ?, ?)
                ''', (lat, lon, elevation, roughness))
                
                # Calculate viewshed
                viewshed_data = calculate_viewshed_for_point(
                    dem_data, dem_transform, lat, lon, elevation
                )
                
                # Store viewshed data for each azimuth
                for azimuth, blocking_profile in viewshed_data.items():
                    max_dist = blocking_profile[-1]['distance_km'] if blocking_profile else 0.0
                    blocking_blob = pickle.dumps(blocking_profile)
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO viewshed 
                        (grid_lat, grid_lon, elevation, azimuth, max_distance_km, blocking_data)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (lat, lon, elevation, azimuth, max_dist, blocking_blob))
                
                pbar.update(1)
                
                # Commit every 100 points
                if pbar.n % 100 == 0:
                    conn.commit()
    
    conn.commit()
    print("Pre-computation complete!")

def generate_statistics(conn):
    """Generate statistics about the pre-computed data."""
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM grid_points')
    num_points = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM viewshed')
    num_viewsheds = cursor.fetchone()[0]
    
    cursor.execute('SELECT AVG(elevation), MIN(elevation), MAX(elevation) FROM grid_points')
    avg_elev, min_elev, max_elev = cursor.fetchone()
    
    print("\n" + "="*60)
    print("PRE-COMPUTATION STATISTICS")
    print("="*60)
    print(f"Grid points: {num_points:,}")
    print(f"Viewshed entries: {num_viewsheds:,}")
    print(f"Elevation range: {min_elev:.0f}m - {max_elev:.0f}m (avg: {avg_elev:.0f}m)")
    print(f"Database size: {Path(conn.execute('PRAGMA database_list').fetchone()[2]).stat().st_size / 1024 / 1024:.1f} MB")
    print("="*60)

def main():
    parser = argparse.ArgumentParser(description='Pre-compute Nevada terrain viewshed database')
    parser.add_argument('--resolution', type=float, default=5.0, 
                       help='Grid spacing in km (default: 5km)')
    parser.add_argument('--output', type=str, default='nevada_viewshed.db',
                       help='Output database file')
    parser.add_argument('--skip-download', action='store_true',
                       help='Skip DEM download if nevada_dem.tif exists')
    
    args = parser.parse_args()
    
    print("="*60)
    print("NEVADA RF COVERAGE PRE-COMPUTATION")
    print("="*60)
    print(f"Grid resolution: {args.resolution} km")
    print(f"Output database: {args.output}")
    print("="*60)
    
    # Download DEM if needed
    dem_file = 'nevada_dem.tif'
    if not args.skip_download or not Path(dem_file).exists():
        dem_file = download_nevada_dem()
    else:
        print(f"Using existing DEM file: {dem_file}")
    
    # Create database
    conn = create_viewshed_database(args.output)
    
    # Pre-compute grid
    precompute_nevada_grid(conn, dem_file, args.resolution)
    
    # Generate statistics
    generate_statistics(conn)
    
    conn.close()
    
    print(f"\nPre-computation complete! Database saved to: {args.output}")
    print("\nTo use this database, update config.py with:")
    print(f"    'viewshed_db': '{args.output}'")

if __name__ == '__main__':
    main()

