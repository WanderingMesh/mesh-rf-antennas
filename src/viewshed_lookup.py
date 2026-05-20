"""
Fast viewshed lookup from pre-computed Nevada database.

This module provides instant terrain blocking information by querying
the pre-computed viewshed database instead of calculating in real-time.
"""

import sqlite3
import numpy as np
from pathlib import Path
from typing import Tuple, Optional
import pickle


class ViewshedLookup:
    """
    Fast lookup of pre-computed viewshed data.
    
    This class queries the Nevada viewshed database to retrieve terrain
    blocking information for any location in Nevada.
    """
    
    def __init__(self, db_path: str = 'nevada_viewshed.db'):
        """
        Initialize viewshed lookup.
        
        Args:
            db_path: Path to the pre-computed viewshed database
        """
        self.db_path = Path(db_path)
        
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Viewshed database not found: {self.db_path}\n"
                f"Run precompute_nevada.py to generate it."
            )
        
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        
        # Cache for grid points
        self._grid_cache = {}
    
    def get_nearest_grid_point(self, lat: float, lon: float) -> Optional[Tuple[int, float, float, float]]:
        """
        Find the nearest pre-computed grid point.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Tuple of (grid_id, grid_lat, grid_lon, grid_elevation) or None
        """
        # Check cache first
        cache_key = (round(lat, 4), round(lon, 4))
        if cache_key in self._grid_cache:
            return self._grid_cache[cache_key]
        
        # Query database for nearest point
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, lat, lon, elevation,
                   ((lat - ?) * (lat - ?) + (lon - ?) * (lon - ?)) as dist_sq
            FROM grid_points
            ORDER BY dist_sq
            LIMIT 1
        ''', (lat, lat, lon, lon))
        
        result = cursor.fetchone()
        
        if result:
            grid_id, grid_lat, grid_lon, grid_elev, _ = result
            value = (grid_id, grid_lat, grid_lon, grid_elev)
            self._grid_cache[cache_key] = value
            return value
        
        return None
    
    def get_viewshed_data(self, grid_id: int) -> np.ndarray:
        """
        Get viewshed data for a grid point.
        
        Args:
            grid_id: Grid point ID
            
        Returns:
            Array of shape (num_azimuths, max_distance) with terrain blocking data
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT azimuth, viewshed_data
            FROM viewshed_data
            WHERE grid_id = ?
            ORDER BY azimuth
        ''', (grid_id,))
        
        rows = cursor.fetchall()
        
        if not rows:
            return None
        
        # Deserialize viewshed data
        viewshed_list = []
        for azimuth, data_blob in rows:
            data = pickle.loads(data_blob)
            viewshed_list.append(data)
        
        return np.array(viewshed_list)
    
    def get_terrain_loss_fast(self, tx_lat: float, tx_lon: float, 
                              rows: np.ndarray, cols: np.ndarray,
                              distances_km: np.ndarray, 
                              dem_transform: Tuple) -> np.ndarray:
        """
        Get terrain loss using pre-computed viewshed data.
        
        This is MUCH faster than real-time radial sweep analysis.
        
        Args:
            tx_lat: Transmitter latitude
            tx_lon: Transmitter longitude
            rows: Row indices of receiver pixels
            cols: Column indices of receiver pixels
            distances_km: Distances from transmitter to receivers (km)
            dem_transform: DEM transform for coordinate conversion
            
        Returns:
            Array of terrain loss values (dB)
        """
        # Find nearest grid point
        grid_info = self.get_nearest_grid_point(tx_lat, tx_lon)
        
        if grid_info is None:
            # Fallback to simple atmospheric loss
            return 0.5 * distances_km
        
        grid_id, grid_lat, grid_lon, grid_elev = grid_info
        
        # Get raw viewshed data from database
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT azimuth, viewshed_data
            FROM viewshed_data
            WHERE grid_id = ?
            ORDER BY azimuth
        ''', (grid_id,))
        
        rows_data = cursor.fetchall()
        
        if not rows_data:
            # Fallback to simple atmospheric loss
            return 0.5 * distances_km
        
        # Deserialize viewshed data - it's a dict of azimuth -> blocking profile
        viewshed_by_azimuth = {}
        for azimuth, data_blob in rows_data:
            blocking_profile = pickle.loads(data_blob)
            viewshed_by_azimuth[azimuth] = blocking_profile
        
        # Calculate azimuths from transmitter to all receivers
        # Convert pixel coordinates to lat/lon
        from affine import Affine
        transform = Affine.from_gdal(*dem_transform)
        
        rx_lons, rx_lats = transform * (cols, rows)
        
        # Calculate azimuths
        delta_lon = rx_lons - tx_lon
        delta_lat = rx_lats - tx_lat
        azimuths = np.degrees(np.arctan2(delta_lon, delta_lat)) % 360
        
        # Initialize terrain loss
        terrain_loss = 0.5 * distances_km  # Base atmospheric loss
        
        # Antenna heights
        tx_antenna_height = 10.0
        rx_antenna_height = 2.0
        
        # Vectorized terrain blocking lookup
        # For each receiver, interpolate between nearest azimuths for smoother results
        azimuth_keys = sorted(viewshed_by_azimuth.keys())
        
        # Pre-calculate receiver elevation angles
        rx_elev_angles = np.degrees(np.arctan2(rx_antenna_height, distances_km * 1000))
        
        # Process in chunks for better performance
        chunk_size = 1000
        for chunk_start in range(0, len(rows), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(rows))
            
            for i in range(chunk_start, chunk_end):
                receiver_azimuth = azimuths[i]
                receiver_distance_km = distances_km[i]
                
                # Find two nearest azimuths for interpolation
                az_diffs = [(abs(az - receiver_azimuth), abs(az - receiver_azimuth + 360), 
                           abs(az - receiver_azimuth - 360)) for az in azimuth_keys]
                az_min_diffs = [min(diffs) for diffs in az_diffs]
                
                # Get nearest azimuth
                nearest_idx = np.argmin(az_min_diffs)
                nearest_az = azimuth_keys[nearest_idx]
                
                blocking_profile = viewshed_by_azimuth[nearest_az]
                
                if not blocking_profile:
                    continue
                
                # Find the highest blocking point along the path
                max_blocking_angle = -90.0
                
                for block in blocking_profile:
                    block_dist_km = block['distance_km']
                    block_elev_angle = block['elevation_angle']
                    
                    # Only consider blocking points between TX and RX
                    if block_dist_km < receiver_distance_km:
                        max_blocking_angle = max(max_blocking_angle, block_elev_angle)
                
                # Check if receiver is blocked
                if rx_elev_angles[i] < max_blocking_angle:
                    # Receiver is in terrain shadow
                    shadow_depth = max_blocking_angle - rx_elev_angles[i]
                    # Add significant loss for terrain blocking
                    terrain_loss[i] += 20.0 + 3.0 * min(shadow_depth, 10.0)
        
        return terrain_loss
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()
