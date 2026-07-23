#!/usr/bin/env python3
"""
Digital Elevation Model (DEM) Handler

This module handles DEM data acquisition, processing, and terrain analysis
for the Longley-Rice RF coverage application. It provides functions for
downloading SRTM data, processing terrain profiles, and calculating
line-of-sight analysis.

Features:
- SRTM DEM data download and caching
- Terrain profile extraction along propagation paths
- Line-of-sight calculations with Fresnel zone clearance
- Coordinate transformations between lat/lon and pixel coordinates
- Terrain roughness and statistical analysis
"""

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling
import elevation
import os
import sys
from pathlib import Path
from typing import Tuple, Optional, Dict
import warnings
warnings.filterwarnings('ignore')


class DEMHandler:
    """
    Handles DEM data acquisition, processing, and terrain analysis.
    
    This class provides methods for downloading SRTM data, processing
    terrain profiles, and performing line-of-sight calculations for
    RF propagation analysis.
    """
    
    def __init__(self, cache_dir: str = "dem_cache", resolution: int = 90):
        """
        Initialize DEM handler.
        
        Args:
            cache_dir: Directory to cache DEM data
            resolution: DEM resolution in meters (30, 90, or 250)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.resolution = resolution
        
        # Supported resolutions
        self.supported_resolutions = [30, 90, 250]
        if resolution not in self.supported_resolutions:
            raise ValueError(f"Resolution must be one of {self.supported_resolutions}")
    
    def get_dem_data(self, bounds: Tuple[float, float, float, float], 
                    force_download: bool = False) -> Tuple[np.ndarray, rasterio.transform.Affine]:
        """
        Get DEM data for the specified bounds.
        
        Args:
            bounds: (west, south, east, north) in decimal degrees
            force_download: Force download even if cached data exists
        
        Returns:
            Tuple of (dem_array, transform)
        """
        west, south, east, north = bounds
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate cache filename with absolute path
        cache_file = self.cache_dir.absolute() / f"dem_{west:.4f}_{south:.4f}_{east:.4f}_{north:.4f}_{self.resolution}m.tif"
        
        # Check if cached data exists
        if cache_file.exists() and not force_download:
            print(f"Loading cached DEM data: {cache_file}")
            with rasterio.open(cache_file) as src:
                dem_data = src.read(1)
                transform = src.transform
                return dem_data, transform
        
        # Download DEM data
        print(f"Downloading DEM data for bounds: {bounds}")
        print(f"Resolution: {self.resolution}m")
        
        try:
            # Download SRTM data - use correct product name
            if self.resolution == 30:
                product = 'SRTM1'  # 1 arc-second (30m)
            elif self.resolution == 90:
                product = 'SRTM3'  # 3 arc-second (90m)
            else:
                product = 'SRTM3'  # Default to 90m
            
            print(f"Downloading {product} data...")
            # The elevation library invokes `make`, which shells out to the GDAL
            # command-line tools (gdal_translate, gdalbuildvrt). Those binaries live
            # in the active conda env's bin directory, but a subprocess only inherits
            # the system PATH. Inject the interpreter's bin dir so the download works
            # regardless of how the app was launched (IDE, cron, activated shell, etc.).
            conda_bin = str(Path(sys.executable).parent)
            env_path = os.environ.get('PATH', '')
            if conda_bin not in env_path.split(os.pathsep):
                os.environ['PATH'] = conda_bin + os.pathsep + env_path
            elevation.clip(bounds=bounds, output=str(cache_file), product=product)
            
            # Load the downloaded data
            with rasterio.open(cache_file) as src:
                dem_data = src.read(1)
                transform = src.transform
                
            print(f"DEM data downloaded and cached: {cache_file}")
            print(f"DEM shape: {dem_data.shape}")
            print(f"Elevation range: {dem_data.min():.1f}m to {dem_data.max():.1f}m")
            
            return dem_data, transform
            
        except Exception as e:
            print(f"Error downloading DEM data: {e}")
            # Clean the elevation cache so the next run doesn't find stale zero-byte
            # tiles left behind by the `|| touch` fallbacks in the elevation Makefile.
            # Without this, subsequent attempts skip the download step entirely because
            # make considers the (empty) target files up-to-date.
            try:
                elevation.clean(product=product)
                print("Elevation cache cleaned - next run will re-download from scratch.")
            except Exception as clean_err:
                print(f"Warning: could not clean elevation cache: {clean_err}")
            print("CRITICAL: Cannot proceed without terrain data!")
            raise RuntimeError(f"Failed to download terrain data: {e}")
    
    def _create_fallback_dem(self, bounds: Tuple[float, float, float, float]) -> Tuple[np.ndarray, rasterio.transform.Affine]:
        """Create a fallback flat DEM when download fails."""
        west, south, east, north = bounds
        
        # Create a simple flat terrain
        # Calculate approximate pixel size
        lat_span = north - south
        lon_span = east - west
        
        # Estimate pixel dimensions
        pixels_per_degree = 111320 / self.resolution  # Approximate
        height = int(lat_span * pixels_per_degree)
        width = int(lon_span * pixels_per_degree)
        
        # Create flat terrain at 100m elevation
        dem_data = np.full((height, width), 100.0, dtype=np.float32)
        
        # Create transform
        transform = from_bounds(west, south, east, north, width, height)
        
        print("Using fallback flat terrain (100m elevation)")
        return dem_data, transform
    
    def latlon_to_pixel(self, lat: float, lon: float, transform: rasterio.transform.Affine) -> Tuple[int, int]:
        """
        Convert latitude/longitude to pixel coordinates.
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            transform: Rasterio transform
        
        Returns:
            Tuple of (row, col) pixel coordinates
        """
        col, row = rasterio.transform.rowcol(transform, lon, lat)
        return row, col
    
    def pixel_to_latlon(self, row: int, col: int, transform: rasterio.transform.Affine) -> Tuple[float, float]:
        """
        Convert pixel coordinates to latitude/longitude.
        
        Args:
            row: Row pixel coordinate
            col: Column pixel coordinate
            transform: Rasterio transform
        
        Returns:
            Tuple of (lat, lon) in decimal degrees
        """
        lon, lat = rasterio.transform.xy(transform, row, col)
        return lat, lon
    
    def get_terrain_profile(self, tx_lat: float, tx_lon: float, tx_elev_m: float,
                           rx_lat: float, rx_lon: float, dem_data: np.ndarray,
                           transform: rasterio.transform.Affine, 
                           num_points: int = 50) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract terrain profile along the path between transmitter and receiver.
        
        Args:
            tx_lat: Transmitter latitude
            tx_lon: Transmitter longitude
            tx_elev_m: Transmitter elevation in meters
            rx_lat: Receiver latitude
            rx_lon: Receiver longitude
            dem_data: DEM data array
            transform: DEM transform
            num_points: Number of points along the profile
        
        Returns:
            Tuple of (terrain_heights, distances) where:
            - terrain_heights: Array of terrain heights in meters
            - distances: Array of distances in kilometers
        """
        # Calculate total distance
        total_distance = self._haversine_distance(tx_lat, tx_lon, rx_lat, rx_lon) / 1000
        
        # Create distance array
        distances = np.linspace(0, total_distance, num_points)
        
        # Sample terrain heights along the path
        terrain_heights = []
        
        for i, dist in enumerate(distances):
            if i == 0:
                # Transmitter location
                terrain_heights.append(tx_elev_m)
            elif i == num_points - 1:
                # Receiver location - use DEM data
                rx_row, rx_col = self.latlon_to_pixel(rx_lat, rx_lon, transform)
                if (0 <= rx_row < dem_data.shape[0] and 0 <= rx_col < dem_data.shape[1]):
                    terrain_heights.append(dem_data[rx_row, rx_col])
                else:
                    terrain_heights.append(tx_elev_m)  # Fallback
            else:
                # Interpolate along the path
                frac = dist / total_distance
                lat = tx_lat + frac * (rx_lat - tx_lat)
                lon = tx_lon + frac * (rx_lon - tx_lon)
                
                # Get terrain height at this point
                row, col = self.latlon_to_pixel(lat, lon, transform)
                if (0 <= row < dem_data.shape[0] and 0 <= col < dem_data.shape[1]):
                    terrain_heights.append(dem_data[row, col])
                else:
                    # Use nearest valid pixel
                    row = max(0, min(dem_data.shape[0] - 1, row))
                    col = max(0, min(dem_data.shape[1] - 1, col))
                    terrain_heights.append(dem_data[row, col])
        
        return np.array(terrain_heights), distances
    
    def check_line_of_sight(self, dem_data: np.ndarray, transform: rasterio.transform.Affine,
                           tx_lat: float, tx_lon: float, tx_elev_m: float,
                           rx_lat: float, rx_lon: float, rx_elev_m: float = 1.5,
                           fresnel_clearance: float = 0.6) -> Tuple[bool, float]:
        """
        Check line of sight between transmitter and receiver.
        
        Args:
            dem_data: DEM data array
            transform: DEM transform
            tx_lat: Transmitter latitude
            tx_lon: Transmitter longitude
            tx_elev_m: Transmitter elevation in meters
            rx_lat: Receiver latitude
            rx_lon: Receiver longitude
            rx_elev_m: Receiver elevation in meters
            fresnel_clearance: Required Fresnel zone clearance (0.6 = 60%)
        
        Returns:
            Tuple of (has_los, obstruction_loss_db)
        """
        # Get terrain profile
        terrain_heights, distances = self.get_terrain_profile(
            tx_lat, tx_lon, tx_elev_m, rx_lat, rx_lon, dem_data, transform
        )
        
        # Calculate line-of-sight heights
        total_distance = distances[-1]
        los_heights = tx_elev_m + (rx_elev_m - tx_elev_m) * (distances / total_distance)
        
        # Check for obstructions
        obstacles = terrain_heights - los_heights
        max_obstruction = np.max(obstacles)
        
        if max_obstruction <= 0:
            # No obstructions
            return True, 0.0
        
        # Calculate Fresnel zone radius at the point of maximum obstruction
        max_obstruction_idx = np.argmax(obstacles)
        d1 = distances[max_obstruction_idx]
        d2 = total_distance - d1
        
        # Use 900 MHz as default frequency for Fresnel calculation
        frequency_hz = 900e6
        wavelength = 3e8 / frequency_hz
        fresnel_radius = np.sqrt(wavelength * d1 * 1000 * d2 * 1000 / (d1 + d2) / 1000)
        
        # Check if obstruction exceeds Fresnel clearance
        required_clearance = fresnel_clearance * fresnel_radius
        
        if max_obstruction <= required_clearance:
            # Line of sight maintained with adequate Fresnel clearance
            return True, 0.0
        else:
            # Line of sight blocked
            # Calculate obstruction loss (simplified model)
            obstruction_loss = 20 * np.log10(max_obstruction / required_clearance)
            return False, obstruction_loss
    
    def calculate_terrain_roughness(self, dem_data: np.ndarray, 
                                   window_size: int = 3) -> np.ndarray:
        """
        Calculate terrain roughness using standard deviation of elevation.
        
        Args:
            dem_data: DEM data array
            window_size: Size of the moving window for roughness calculation
        
        Returns:
            Array of terrain roughness values
        """
        from scipy import ndimage
        
        # Calculate standard deviation in a moving window
        roughness = ndimage.generic_filter(
            dem_data, 
            np.std, 
            size=window_size,
            mode='constant',
            cval=np.nan
        )
        
        return roughness
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great circle distance between two points."""
        R = 6371000  # Earth radius in meters
        
        phi1 = np.radians(lat1)
        phi2 = np.radians(lat2)
        delta_phi = np.radians(lat2 - lat1)
        delta_lambda = np.radians(lon2 - lon1)
        
        a = (np.sin(delta_phi/2)**2 + 
             np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda/2)**2)
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        
        return R * c


def create_dem_bounds(center_lat: float, center_lon: float, 
                     radius_km: float) -> Tuple[float, float, float, float]:
    """
    Create DEM bounds around a center point.
    
    Args:
        center_lat: Center latitude
        center_lon: Center longitude
        radius_km: Radius in kilometers
    
    Returns:
        Tuple of (west, south, east, north) bounds
    """
    # Approximate conversion from km to degrees
    # 1 degree latitude ≈ 111 km
    # 1 degree longitude ≈ 111 km * cos(latitude)
    
    lat_offset = radius_km / 111.0
    lon_offset = radius_km / (111.0 * np.cos(np.radians(center_lat)))
    
    west = center_lon - lon_offset
    east = center_lon + lon_offset
    south = center_lat - lat_offset
    north = center_lat + lat_offset
    
    return (west, south, east, north)
