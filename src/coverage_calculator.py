#!/usr/bin/env python3
"""
Coverage Calculator for Longley-Rice RF Propagation

This module provides the main coverage calculation engine that integrates
the Longley-Rice propagation model with terrain data to generate RF
coverage maps for single sites and multi-site networks.

Features:
- Single site coverage calculation
- Multi-site coverage with additive processing
- Terrain-aware propagation modeling
- Coverage map generation and visualization
- Statistical analysis and reporting
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from .splat_longley_rice import SPLATLongleyRice, calculate_splat_coverage_map
from .dem_handler import DEMHandler, create_dem_bounds
from .splat_service import SplatService


class CoverageCalculator:
    """
    Main coverage calculation engine using Longley-Rice propagation model.
    
    This class provides methods for calculating RF coverage maps for single
    sites and multi-site networks with terrain awareness and statistical
    analysis.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the coverage calculator.
        
        Args:
            config: Configuration dictionary with RF parameters
        """
        self.config = config
        self.dem_handler = DEMHandler(
            cache_dir=config.get('dem_cache_dir', 'dem_cache'),
            resolution=config.get('dem_resolution', 90)
        )
        
        # Check for pre-computed viewshed database
        self.viewshed_db_path = config.get('viewshed_db', None)
        if self.viewshed_db_path:
            from pathlib import Path
            if not Path(self.viewshed_db_path).exists():
                print(f"Warning: Viewshed database not found: {self.viewshed_db_path}")
                print("Falling back to real-time terrain analysis.")
                self.viewshed_db_path = None
        
        # Initialize SPLAT! service if available
        try:
            splat_dir = config.get('splat_dir', 'splat_src/splat-1.4.2')
            self.splat_service = SplatService(splat_dir=splat_dir)
            print(f"SPLAT! service initialized - using real SPLAT! binary for calculations")
        except Exception as e:
            print(f"SPLAT! service not available: {e}")
            print("Falling back to Python implementation")
            self.splat_service = None
        
        # RF parameters - check both top-level and 'rf' sub-dict for backwards compatibility
        rf_config = config.get('rf', config)
        self.frequency_mhz = rf_config.get('frequency_mhz', 900.0)
        self.tx_power_dbm = rf_config.get('tx_power_dbm', 30.0)
        self.antenna_gain_dbi = rf_config.get('antenna_gain_dbi', 0.0)
        self.antenna_type = rf_config.get('antenna_type', 'omnidirectional')
        self.antenna_azimuth = rf_config.get('antenna_azimuth', 0.0)
        self.antenna_tilt = rf_config.get('antenna_tilt', 0.0)
        self.antenna_tilt_azimuth = rf_config.get('antenna_tilt_azimuth', 0.0)
        self.rx_sensitivity_dbm = rf_config.get('rx_sensitivity_dbm', -100.0)
        self.fade_margin_db = rf_config.get('fade_margin_db', 3.0)
        
        # DEM parameters
        dem_config = config.get('dem', config)
        self.analysis_radius_km = dem_config.get('analysis_radius_km', 50.0)
        self.pixel_size_km = dem_config.get('pixel_size_km', 0.1)
        
        # Climate zone for Longley-Rice model
        self.climate_zone = rf_config.get('climate_zone', 'continental_temperate')
    
    def calculate_single_site_coverage(self, site_name: str, lat: float, lon: float, 
                                     elev_m: float, progress_callback=None) -> Dict:
        """
        Calculate coverage for a single site.
        
        Args:
            site_name: Name of the site
            lat: Site latitude
            lon: Site longitude
            elev_m: Site elevation in meters
            progress_callback: Optional callback function(progress_pct, message)
        
        Returns:
            Dictionary with coverage data
        """
        if progress_callback:
            progress_callback(10.0, f"Starting calculation for {site_name}")
        
        print(f"Calculating coverage for site: {site_name}")
        print(f"Location: {lat:.6f}, {lon:.6f}")
        print(f"Elevation: {elev_m:.1f}m")
        print(f"Frequency: {self.frequency_mhz} MHz")
        print(f"Power: {self.tx_power_dbm} dBm")
        
        # Create DEM bounds around the site
        bounds = create_dem_bounds(lat, lon, self.analysis_radius_km)
        print(f"DEM bounds: {bounds}")
        
        if progress_callback:
            progress_callback(20.0, "Downloading terrain data...")
        
        # Get DEM data
        dem_data, dem_transform = self.dem_handler.get_dem_data(bounds)
        
        if progress_callback:
            progress_callback(30.0, "Analyzing terrain and calculating propagation...")
        
        # Use SPLAT! binary if available, otherwise fall back to Python implementation
        if self.splat_service:
            print("Using actual SPLAT! binary for realistic coverage calculation")
            coverage_data = self.splat_service.calculate_coverage(
                tx_lat=lat,
                tx_lon=lon,
                tx_elev_m=elev_m,
                frequency_mhz=self.frequency_mhz,
                tx_power_dbm=self.tx_power_dbm,
                antenna_gain_dbi=self.antenna_gain_dbi,
                antenna_type=self.antenna_type,
                antenna_azimuth=self.antenna_azimuth,
                antenna_tilt=self.antenna_tilt,
                antenna_tilt_azimuth=self.antenna_tilt_azimuth,
                rx_sensitivity_dbm=self.rx_sensitivity_dbm,
                analysis_radius_km=self.analysis_radius_km,
                climate_zone=self.climate_zone,
                progress_callback=progress_callback
            )
        else:
            print("Using Python implementation (SPLAT! binary not available)")
            # Calculate coverage map using SPLAT! compatible method
            coverage_data = calculate_splat_coverage_map(
                tx_lat=lat,
                tx_lon=lon,
                tx_elev_m=elev_m,
                dem_data=dem_data,
                dem_transform=dem_transform,
                frequency_mhz=self.frequency_mhz,
                tx_power_dbm=self.tx_power_dbm,
                rx_sensitivity_dbm=self.rx_sensitivity_dbm,
                analysis_radius_km=self.analysis_radius_km,
                pixel_size_km=self.pixel_size_km,
                progress_callback=progress_callback,
                viewshed_db_path=self.viewshed_db_path
            )
        
        if progress_callback:
            progress_callback(95.0, "Finalizing results...")
        
        # Convert lists back to numpy arrays for processing
        coverage_data['coverage_mask'] = np.array(coverage_data['coverage_mask'], dtype=bool)
        coverage_data['signal_strength'] = np.array(coverage_data['signal_strength'], dtype=np.float32)
        
        # Add metadata (don't include config - it has non-serializable objects)
        coverage_data.update({
            'site_name': site_name,
            'dem_bounds': bounds,
            'dem_transform': list(dem_transform),  # Convert transform to list
            'calculated_at': datetime.now().isoformat()
        })
        
        # Calculate statistics
        stats = self._calculate_coverage_statistics(coverage_data)
        coverage_data['statistics'] = stats
        
        print(f"Coverage calculation complete!")
        print(f"Coverage area: {stats['coverage_area_km2']:.1f} km²")
        print(f"Coverage pixels: {stats['coverage_pixels']:,}")
        
        return coverage_data
    
    def calculate_multi_site_coverage(self, sites_df: pd.DataFrame, 
                                    show_nodes: bool = True) -> Dict:
        """
        Calculate coverage for multiple sites.
        
        Args:
            sites_df: DataFrame with site data (name, lat, lon, elev)
            show_nodes: Whether to show node locations on the map
        
        Returns:
            Dictionary with combined coverage data
        """
        print(f"Calculating multi-site coverage for {len(sites_df)} sites")
        
        # Determine overall bounds
        bounds = self._calculate_overall_bounds(sites_df)
        print(f"Overall bounds: {bounds}")
        
        # Get DEM data for the entire area
        dem_data, dem_transform = self.dem_handler.get_dem_data(bounds)
        
        # Calculate coverage for each site
        site_coverage_data = {}
        combined_coverage_mask = np.zeros(dem_data.shape, dtype=bool)
        combined_signal_strength = np.full(dem_data.shape, -200.0, dtype=np.float32)
        node_locations = []
        
        for idx, site in sites_df.iterrows():
            site_name = site['name']
            lat = site['lat']
            lon = site['lon']
            elev_m = site['elev']
            
            print(f"Processing site: {site_name}")
            
            # Calculate coverage for this site using SPLAT! compatible method
            site_data = calculate_splat_coverage_map(
                tx_lat=lat,
                tx_lon=lon,
                tx_elev_m=elev_m,
                dem_data=dem_data,
                dem_transform=dem_transform,
                frequency_mhz=self.frequency_mhz,
                tx_power_dbm=self.tx_power_dbm,
                rx_sensitivity_dbm=self.rx_sensitivity_dbm,
                analysis_radius_km=self.analysis_radius_km,
                pixel_size_km=self.pixel_size_km,
                viewshed_db_path=self.viewshed_db_path
            )
            
            # Convert lists back to numpy arrays for processing
            site_data['coverage_mask'] = np.array(site_data['coverage_mask'], dtype=bool)
            site_data['signal_strength'] = np.array(site_data['signal_strength'], dtype=np.float32)
            
            # Store individual site data
            site_coverage_data[site_name] = site_data
            
            # Add to combined coverage
            combined_coverage_mask |= site_data['coverage_mask']
            
            # Update signal strength (keep maximum)
            combined_signal_strength = np.maximum(
                combined_signal_strength, 
                site_data['signal_strength']
            )
            
            # Store node location
            if show_nodes:
                node_locations.append({
                    'name': site_name,
                    'lat': lat,
                    'lon': lon,
                    'elev': elev_m
                })
        
        # Create combined coverage data (don't include config - it has non-serializable objects)
        combined_data = {
            'coverage_mask': combined_coverage_mask.tolist(),  # Convert to list
            'signal_strength': combined_signal_strength.tolist(),  # Convert to list
            'site_coverage_data': site_coverage_data,
            'node_locations': node_locations,
            'show_nodes': show_nodes,
            'dem_bounds': bounds,
            'dem_transform': list(dem_transform),  # Convert transform to list
            'calculated_at': datetime.now().isoformat()
        }
        
        # Calculate statistics
        stats = self._calculate_multi_site_statistics(combined_data)
        combined_data['statistics'] = stats
        
        print(f"Multi-site coverage calculation complete!")
        print(f"Total coverage area: {stats['total_coverage_area_km2']:.1f} km²")
        print(f"Number of sites: {len(sites_df)}")
        
        return combined_data
    
    def _calculate_overall_bounds(self, sites_df: pd.DataFrame) -> Tuple[float, float, float, float]:
        """Calculate overall bounds for all sites."""
        # Add buffer around all sites
        buffer_km = self.analysis_radius_km + 10  # Extra 10km buffer
        
        min_lat = sites_df['lat'].min()
        max_lat = sites_df['lat'].max()
        min_lon = sites_df['lon'].min()
        max_lon = sites_df['lon'].max()
        
        # Add buffer
        lat_buffer = buffer_km / 111.0
        lon_buffer = buffer_km / (111.0 * np.cos(np.radians((min_lat + max_lat) / 2)))
        
        return (min_lon - lon_buffer, min_lat - lat_buffer,
                max_lon + lon_buffer, max_lat + lat_buffer)
    
    def _calculate_coverage_statistics(self, coverage_data: Dict) -> Dict:
        """Calculate statistics for single site coverage."""
        coverage_mask = np.array(coverage_data['coverage_mask'], dtype=bool)
        signal_strength = np.array(coverage_data['signal_strength'], dtype=np.float32)
        
        # Basic statistics
        total_pixels = coverage_mask.size
        coverage_pixels = np.sum(coverage_mask)
        coverage_percentage = (coverage_pixels / total_pixels) * 100
        
        # Calculate coverage area
        pixel_area_km2 = self.pixel_size_km ** 2
        coverage_area_km2 = coverage_pixels * pixel_area_km2
        
        # Signal strength statistics
        valid_signals = signal_strength[coverage_mask]
        if len(valid_signals) > 0:
            min_signal = np.min(valid_signals)
            max_signal = np.max(valid_signals)
            mean_signal = np.mean(valid_signals)
            std_signal = np.std(valid_signals)
        else:
            min_signal = max_signal = mean_signal = std_signal = 0.0
        
        return {
            'total_pixels': int(total_pixels),
            'coverage_pixels': int(coverage_pixels),
            'coverage_percentage': float(coverage_percentage),
            'coverage_area_km2': float(coverage_area_km2),
            'coverage_area_sqmi': float(coverage_area_km2 * 0.386102),
            'min_signal_dbm': float(min_signal),
            'max_signal_dbm': float(max_signal),
            'mean_signal_dbm': float(mean_signal),
            'std_signal_dbm': float(std_signal)
        }
    
    def _calculate_multi_site_statistics(self, coverage_data: Dict) -> Dict:
        """Calculate statistics for multi-site coverage."""
        coverage_mask = np.array(coverage_data['coverage_mask'], dtype=bool)
        signal_strength = np.array(coverage_data['signal_strength'], dtype=np.float32)
        site_coverage_data = coverage_data['site_coverage_data']
        
        # Basic statistics
        total_pixels = coverage_mask.size
        coverage_pixels = np.sum(coverage_mask)
        coverage_percentage = (coverage_pixels / total_pixels) * 100
        
        # Calculate coverage area
        pixel_area_km2 = self.pixel_size_km ** 2
        total_coverage_area_km2 = coverage_pixels * pixel_area_km2
        
        # Individual site statistics
        site_stats = {}
        for site_name, site_data in site_coverage_data.items():
            site_mask = np.array(site_data['coverage_mask'], dtype=bool)
            site_pixels = np.sum(site_mask)
            site_area_km2 = site_pixels * pixel_area_km2
            
            site_stats[site_name] = {
                'coverage_pixels': int(site_pixels),
                'coverage_area_km2': float(site_area_km2),
                'coverage_area_sqmi': float(site_area_km2 * 0.386102)
            }
        
        # Signal strength statistics
        valid_signals = signal_strength[coverage_mask]
        if len(valid_signals) > 0:
            min_signal = np.min(valid_signals)
            max_signal = np.max(valid_signals)
            mean_signal = np.mean(valid_signals)
            std_signal = np.std(valid_signals)
        else:
            min_signal = max_signal = mean_signal = std_signal = 0.0
        
        return {
            'total_pixels': int(total_pixels),
            'coverage_pixels': int(coverage_pixels),
            'coverage_percentage': float(coverage_percentage),
            'total_coverage_area_km2': float(total_coverage_area_km2),
            'total_coverage_area_sqmi': float(total_coverage_area_km2 * 0.386102),
            'min_signal_dbm': float(min_signal),
            'max_signal_dbm': float(max_signal),
            'mean_signal_dbm': float(mean_signal),
            'std_signal_dbm': float(std_signal),
            'site_statistics': site_stats,
            'number_of_sites': len(site_coverage_data)
        }


def create_coverage_geojson(coverage_mask: np.ndarray, 
                           transform: Tuple,
                           min_area_pixels: int = 100) -> Dict:
    """
    Convert coverage mask to GeoJSON format for web visualization.
    
    Args:
        coverage_mask: Boolean mask where True indicates coverage
        transform: Rasterio transform for coordinate conversion
        min_area_pixels: Minimum polygon area in pixels to include
    
    Returns:
        GeoJSON FeatureCollection with coverage polygons
    """
    try:
        from skimage import measure
        from scipy import ndimage
    except ImportError:
        # Fallback if scikit-image not available
        return {"type": "FeatureCollection", "features": []}
    
    # Clean up the mask
    mask = coverage_mask.astype(bool)
    
    # Remove small holes and noise
    mask = ndimage.binary_fill_holes(mask)
    mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
    
    # Find contours
    contours = measure.find_contours(mask, 0.5)
    
    features = []
    for contour in contours:
        # Convert pixel coordinates to lat/lon
        coords = []
        for row, col in contour:
            # Convert pixel to lat/lon using affine transform
            lon, lat = transform * (col, row)
            coords.append([lon, lat])
        
        # Close the polygon
        if len(coords) > 2:
            coords.append(coords[0])
            
            # Check if polygon is large enough
            if len(coords) >= min_area_pixels:
                feature = {
                    "type": "Feature",
                    "properties": {
                        "coverage": True
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                }
                features.append(feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }
