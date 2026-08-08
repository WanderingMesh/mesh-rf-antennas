#!/usr/bin/env python3
"""
SPLAT! Service Wrapper

This module provides a Python wrapper around the actual SPLAT! binary
for realistic RF propagation modeling with terrain analysis.

Based on the approach used in meshtastic-site-planner but adapted for
our web application with progress tracking, caching, and multi-site support.
"""

import os
import sys
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
import io
import gzip
import math
import logging

from .antenna_patterns import create_pattern_files, get_antenna_info

logger = logging.getLogger(__name__)


class SplatService:
    """
    Wrapper for calling the actual SPLAT! binary for RF propagation analysis.
    
    This provides realistic terrain-aware coverage calculations using the
    industry-standard SPLAT! software.
    """
    
    def __init__(self, splat_dir: str, cache_dir: str = "splat_cache"):
        """
        Initialize SPLAT! service.
        
        Args:
            splat_dir: Directory containing SPLAT! binaries
            cache_dir: Directory for caching terrain tiles
        """
        # Convert to absolute paths
        self.splat_dir = Path(splat_dir).resolve()
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # SPLAT! binaries (absolute paths)
        self.splat_binary = self.splat_dir / "splat"
        self.splat_hd_binary = self.splat_dir / "splat-hd"
        self.srtm2sdf_binary = self.splat_dir / "utils" / "srtm2sdf"
        
        # Verify binaries exist
        if not self.splat_binary.exists():
            raise FileNotFoundError(f"SPLAT! binary not found: {self.splat_binary}")
        if not self.srtm2sdf_binary.exists():
            raise FileNotFoundError(f"srtm2sdf binary not found: {self.srtm2sdf_binary}")
        
        logger.info(f"SPLAT! service initialized with binaries at {splat_dir}")
    
    def calculate_coverage(
        self,
        tx_lat: float,
        tx_lon: float,
        tx_elev_m: float,
        frequency_mhz: float,
        tx_power_dbm: float,
        antenna_gain_dbi: float = 0.0,
        antenna_type: str = "omnidirectional",
        antenna_azimuth: float = 0.0,
        antenna_tilt: float = 0.0,
        antenna_tilt_azimuth: float = 0.0,
        rx_sensitivity_dbm: float = -100.0,
        analysis_radius_km: float = 50.0,
        climate_zone: str = "desert",
        ground_type: str = "desert",
        fraction_of_time: float = 0.50,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Calculate RF coverage using SPLAT!
        
        Args:
            tx_lat: Transmitter latitude
            tx_lon: Transmitter longitude
            tx_elev_m: Transmitter elevation AGL in meters
            frequency_mhz: Frequency in MHz
            tx_power_dbm: Transmitter power in dBm
            antenna_gain_dbi: Antenna gain in dBi
            antenna_type: Antenna type (omnidirectional, yagi_3el, yagi_5el, yagi_11el)
            antenna_azimuth: Antenna pointing direction in degrees (0=North, 90=East)
            antenna_tilt: Mechanical beam tilt in degrees (positive=down, negative=up)
            antenna_tilt_azimuth: Compass direction of tilt in degrees (0=North, 90=East)
            rx_sensitivity_dbm: Receiver sensitivity in dBm
            analysis_radius_km: Analysis radius in km
            climate_zone: Climate zone for propagation model
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with coverage data
        """
        if progress_callback:
            progress_callback(10.0, "Preparing SPLAT! calculation...")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            try:
                # Download and convert terrain tiles
                if progress_callback:
                    progress_callback(20.0, "Downloading terrain data...")
                
                self._prepare_terrain_tiles(tx_lat, tx_lon, analysis_radius_km, tmpdir)
                
                # Create SPLAT! input files
                if progress_callback:
                    progress_callback(30.0, "Creating SPLAT! configuration...")
                
                self._create_qth_file(tmpdir / "tx.qth", "TX", tx_lat, tx_lon, tx_elev_m)
                self._create_lrp_file(
                    tmpdir / "tx.lrp",  # CRITICAL: Must match QTH base name for antenna patterns to work!
                    frequency_mhz=frequency_mhz,
                    tx_power_dbm=tx_power_dbm,
                    antenna_gain_dbi=antenna_gain_dbi,
                    climate_zone=climate_zone,
                    ground_type=ground_type,
                    fraction_of_time=fraction_of_time
                )
                
                # Create antenna pattern files (azimuth and elevation patterns)
                # CRITICAL: site_name must match the site NAME in QTH file, not the filename!
                self._create_antenna_pattern_files(
                    tmpdir,
                    antenna_type=antenna_type,
                    antenna_azimuth=antenna_azimuth,
                    antenna_tilt=antenna_tilt,
                    antenna_tilt_azimuth=antenna_tilt_azimuth
                )
                
                # Run SPLAT!
                if progress_callback:
                    progress_callback(40.0, "Running SPLAT! analysis...")
                
                self._run_splat(
                    tmpdir,
                    radius_km=analysis_radius_km,
                    rx_sensitivity_dbm=rx_sensitivity_dbm
                )
                
                # Parse results
                if progress_callback:
                    progress_callback(80.0, "Processing SPLAT! output...")
                
                coverage_data = self._parse_splat_output(
                    tmpdir / "output.ppm",
                    tmpdir / "output.kml",
                    tx_lat,
                    tx_lon,
                    tx_elev_m,
                    frequency_mhz,
                    tx_power_dbm,
                    antenna_gain_dbi,
                    antenna_type,
                    antenna_azimuth,
                    antenna_tilt,
                    antenna_tilt_azimuth,
                    analysis_radius_km
                )
                
                if progress_callback:
                    progress_callback(100.0, "Complete!")
                
                return coverage_data
                
            except Exception as e:
                logger.error(f"SPLAT! calculation failed: {e}")
                raise RuntimeError(f"SPLAT! calculation failed: {e}")
    
    def _prepare_terrain_tiles(self, lat: float, lon: float, radius_km: float, work_dir: Path):
        """Download and convert terrain tiles for SPLAT!"""
        # Calculate required tiles
        required_tiles = self._calculate_required_tiles(lat, lon, radius_km)
        
        logger.info(f"Need {len(required_tiles)} terrain tiles")
        
        for tile_name, sdf_name in required_tiles:
            sdf_path = work_dir / sdf_name
            
            # Check cache first
            cached_sdf = self.cache_dir / sdf_name
            if cached_sdf.exists():
                logger.info(f"Using cached tile: {sdf_name}")
                # Copy from cache
                import shutil
                shutil.copy(cached_sdf, sdf_path)
                continue
            
            # Download and convert
            logger.info(f"Downloading and converting: {tile_name}")
            hgt_data = self._download_srtm_tile(tile_name)
            
            # Save HGT file temporarily
            hgt_path = work_dir / tile_name.replace(".gz", "")
            with gzip.open(io.BytesIO(hgt_data)) as gz:
                with open(hgt_path, "wb") as f:
                    f.write(gz.read())
            
            # Convert to SDF
            subprocess.run(
                [str(self.srtm2sdf_binary), hgt_path.name],
                cwd=work_dir,
                check=True,
                capture_output=True
            )
            
            # Cache the SDF
            if sdf_path.exists():
                import shutil
                shutil.copy(sdf_path, cached_sdf)
    
    def _calculate_required_tiles(self, lat: float, lon: float, radius_km: float):
        """
        Calculate which SRTM tiles are needed for the analysis area.
        
        CRITICAL: SPLAT! uses a specific SDF filename convention:
        - Format: min_lat:max_lat:min_west:max_west.sdf
        - Longitude is expressed as DEGREES WEST (positive values) for western hemisphere
        - For example, a tile covering 39-40°N, 119-120°W is named: 39:40:119:120.sdf
        
        This differs from the standard geographic convention where west = negative.
        """
        earth_radius = 6378137  # meters
        delta_deg = (radius_km * 1000 / earth_radius) * (180 / math.pi)
        
        lat_min = math.floor(lat - delta_deg)
        lat_max = math.floor(lat + delta_deg)
        lon_min = math.floor(lon - delta_deg / math.cos(math.radians(lat)))
        lon_max = math.floor(lon + delta_deg / math.cos(math.radians(lat)))
        
        tiles = []
        for lat_tile in range(lat_min, lat_max + 1):
            for lon_tile in range(lon_min, lon_max + 1):
                # SRTM tile naming: N/S prefix + lat, E/W prefix + lon
                ns = "N" if lat_tile >= 0 else "S"
                ew = "E" if lon_tile >= 0 else "W"
                tile_name = f"{ns}{abs(lat_tile):02d}{ew}{abs(lon_tile):03d}.hgt.gz"
                
                # SPLAT! SDF filename format uses DEGREES WEST for longitude
                # Format is min_west:max_west where min_west < max_west
                # The tile at lon_tile covers lon_tile to lon_tile+1
                # e.g., lon_tile=-120 covers -120 to -119, which is 119°W to 120°W
                if lon_tile < 0:
                    # Western hemisphere: convert to positive degrees west
                    # lon_tile=-120 spans -120 to -119, i.e., 120°W to 119°W
                    # SPLAT! expects min_west < max_west, so: 119:120
                    min_west = abs(lon_tile + 1)  # Eastern edge (smaller west value)
                    max_west = abs(lon_tile)       # Western edge (larger west value)
                else:
                    # Eastern hemisphere: use 360 - lon convention
                    min_west = 360 - lon_tile - 1
                    max_west = 360 - lon_tile
                
                # Format: min_lat:max_lat:min_west:max_west.sdf
                sdf_name = f"{lat_tile}:{lat_tile+1}:{min_west}:{max_west}.sdf"
                tiles.append((tile_name, sdf_name))
        
        return tiles
    
    def _download_srtm_tile(self, tile_name: str) -> bytes:
        """Download SRTM tile using elevation library directly"""
        import elevation
        import tempfile
        import os
        import struct
        
        # Parse tile name: e.g., "N39W120.hgt.gz"
        lat_str = tile_name[0:3]  # N39
        lon_str = tile_name[3:7]  # W120
        
        lat = int(lat_str[1:])
        if lat_str[0] == 'S':
            lat = -lat
        
        lon = int(lon_str[1:])
        if lon_str[0] == 'W':
            lon = -lon
        
        print(f"Downloading {tile_name} using elevation library...")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use elevation library to download exactly this 1x1 degree tile
            output = os.path.join(tmpdir, "tile.tif")
            bounds = (lon, lat, lon + 1, lat + 1)
            
            try:
                # The elevation library calls `make` as a subprocess, which only inherits
                # the system PATH — not the conda env PATH. gdal_translate lives in the
                # conda env bin directory, so we must inject it into PATH before the call.
                conda_bin = str(Path(sys.executable).parent)
                env_path = os.environ.get('PATH', '')
                if conda_bin not in env_path:
                    os.environ['PATH'] = conda_bin + os.pathsep + env_path
                elevation.clip(bounds=bounds, output=output, product='SRTM3')
            except Exception as e:
                print(f"  Warning: elevation.clip failed: {e}")
                print(f"  Filling with NODATA")
                # Create empty tile
                data = np.full((1201, 1201), -32768, dtype=np.int16)
                hgt_data = bytearray()
                for row in data:
                    for val in row:
                        hgt_data.extend(struct.pack('>h', val))
                import gzip
                return gzip.compress(bytes(hgt_data))
            
            # Read the downloaded tile
            with rasterio.open(output) as src:
                data = src.read(1)
                print(f"  Downloaded shape: {data.shape}")
                print(f"  Elevation range: {data.min():.0f}m to {data.max():.0f}m")
                
                # Resample to exactly 1201x1201 if needed
                if data.shape != (1201, 1201):
                    from rasterio.enums import Resampling
                    from rasterio.warp import reproject, calculate_default_transform
                    
                    # Create output array
                    resampled = np.empty((1201, 1201), dtype=np.float32)
                    
                    # Calculate transforms for exact 1x1 degree at 1201x1201 resolution
                    dst_transform = rasterio.transform.from_bounds(
                        lon, lat, lon + 1, lat + 1, 1201, 1201
                    )
                    
                    # Reproject
                    reproject(
                        source=data,
                        destination=resampled,
                        src_transform=src.transform,
                        dst_transform=dst_transform,
                        src_crs=src.crs,
                        dst_crs='EPSG:4326',
                        resampling=Resampling.bilinear
                    )
                    
                    data = resampled
                    print(f"  Resampled to: {data.shape}")
                
                # Convert to HGT format (big-endian 16-bit signed integers)
                # HGT format: rows from north to south, columns from west to east
                hgt_data = bytearray()
                for row in data:
                    for val in row:
                        # Clamp to int16 range and convert
                        val = int(max(-32768, min(32767, val)))
                        hgt_data.extend(struct.pack('>h', val))
                
                print(f"  Created HGT file: {len(hgt_data)} bytes")
                
                # Compress with gzip
                import gzip
                compressed = gzip.compress(bytes(hgt_data))
                print(f"  Compressed to: {len(compressed)} bytes")
                
                return compressed
    
    def _create_qth_file(self, path: Path, name: str, lat: float, lon: float, elev: float):
        """Create SPLAT! QTH (site) file"""
        # SPLAT! uses west longitude as positive
        splat_lon = abs(lon) if lon < 0 else 360 - lon
        
        # CRITICAL: Must specify units! Without units, SPLAT! assumes feet.
        # Since we're using -metric flag, specify "meters" explicitly
        content = f"{name}\n{lat:.6f}\n{splat_lon:.6f}\n{elev:.2f} meters\n"
        path.write_text(content)
        
        print(f"Created QTH file:")
        print(f"  Name: {name}")
        print(f"  Lat: {lat:.6f}")
        print(f"  Lon (original): {lon:.6f}")
        print(f"  Lon (SPLAT! format): {splat_lon:.6f}")
        print(f"  Antenna height: {elev:.2f} meters")
        print(f"QTH file contents:")
        print(content)
    
    # Ground dielectric constant and conductivity by terrain type.
    # Values from SPLAT! documentation (splat.txt).
    GROUND_PARAMS = {
        "average":       (15.0, 0.005,  "Average Ground (Farmland/Forest)"),
        "poor":          (4.0,  0.001,  "Poor Ground (Rocky/Dry)"),
        "desert":        (13.0, 0.002,  "Desert / Dry Sand"),
        "good":          (25.0, 0.020,  "Good Ground (Rich Soil)"),
        "fresh_water":   (80.0, 0.010,  "Fresh Water"),
        "salt_water":    (80.0, 5.000,  "Salt Water / Salt Flat"),
        "marshy":        (12.0, 0.007,  "Marshy Land"),
        "city":          (5.0,  0.001,  "City / Urban"),
    }

    def _create_lrp_file(self, path: Path, frequency_mhz: float, tx_power_dbm: float, 
                        antenna_gain_dbi: float = 0.0, climate_zone: str = "desert",
                        ground_type: str = "desert", fraction_of_time: float = 0.50):
        """
        Create SPLAT! LRP (Longley-Rice parameters) file.
        
        The ERP (Effective Radiated Power) calculation includes:
        - TX power in dBm
        - Antenna gain in dBi
        - System losses (assumed 0 dB for simplicity)
        
        ERP = TX Power + Antenna Gain - System Loss
        
        Climate zones (from SPLAT! documentation):
        1: Equatorial (Congo)
        2: Continental Subtropical (Sudan)
        3: Maritime Subtropical (West coast of Africa)
        4: Desert (Sahara, Great Basin, Mojave)
        5: Continental Temperate (US interior)
        6: Maritime Temperate, over land (UK, Pacific NW)
        7: Maritime Temperate, over sea (open ocean, coastal)
        """
        climate_codes = {
            "equatorial": 1,
            "continental_subtropical": 2,
            "maritime_subtropical": 3,
            "desert": 4,
            "continental_temperate": 5,
            "maritime_temperate_land": 6,
            "maritime_temperate_sea": 7,
        }
        climate_code = climate_codes.get(climate_zone, 4)
        
        dielectric, conductivity, ground_desc = self.GROUND_PARAMS.get(
            ground_type, self.GROUND_PARAMS["desert"]
        )
        
        # Clamp fraction_of_time to the valid ITM range
        fraction_of_time = max(0.01, min(0.99, fraction_of_time))
        
        system_loss_db = 0.0
        erp_watts = 10 ** ((tx_power_dbm + antenna_gain_dbi - system_loss_db - 30) / 10)
        
        print(f"LRP file parameters:")
        print(f"  TX Power: {tx_power_dbm} dBm")
        print(f"  Antenna Gain: {antenna_gain_dbi} dBi")
        print(f"  System Loss: {system_loss_db} dB")
        print(f"  Calculated ERP: {erp_watts:.4f} watts ({10 * np.log10(erp_watts * 1000):.2f} dBm)")
        print(f"  Climate Zone: {climate_zone} (code {climate_code})")
        print(f"  Ground Type: {ground_desc} (εr={dielectric}, σ={conductivity} S/m)")
        print(f"  Fraction of time: {fraction_of_time}")
        print(f"  Frequency: {frequency_mhz} MHz")
        
        content = f"""{dielectric:.3f}  ; Earth Dielectric Constant ({ground_desc})
{conductivity:.6f}  ; Earth Conductivity S/m ({ground_desc})
301.000  ; Atmospheric Bending Constant (N-units)
{frequency_mhz:.3f}  ; Frequency in MHz
{climate_code}  ; Radio Climate ({climate_zone})
1  ; Polarization (1 = Vertical)
0.50  ; Fraction of situations (0.5 = median/typical)
{fraction_of_time:.2f}  ; Fraction of time
{erp_watts:.4f}  ; ERP in Watts (TX {tx_power_dbm} dBm + Gain {antenna_gain_dbi} dBi)
"""
        path.write_text(content)
        logger.info(f"Created LRP file with ERP={erp_watts:.4f}W, Freq={frequency_mhz}MHz, "
                     f"Ground={ground_type}, Climate={climate_zone}, FoT={fraction_of_time}")
    
    def _create_antenna_pattern_files(self, work_dir: Path, antenna_type: str, antenna_azimuth: float,
                                      antenna_tilt: float = 0.0, antenna_tilt_azimuth: float = 0.0):
        """
        Create antenna pattern files (.az and .el) for SPLAT!
        
        Args:
            work_dir: Working directory for SPLAT! files
            antenna_type: Type of antenna (omnidirectional, yagi_3el, etc.)
            antenna_azimuth: Antenna pointing direction in degrees
            antenna_tilt: Mechanical beam tilt in degrees (positive=down, negative=up)
            antenna_tilt_azimuth: Compass direction of tilt in degrees
        """
        antenna_info = get_antenna_info(antenna_type)
        
        print(f"Creating antenna pattern files:")
        print(f"  Type: {antenna_info['description']}")
        print(f"  Azimuth: {antenna_azimuth}° (0=North, 90=East)")
        print(f"  Tilt: {antenna_tilt}° ({'down' if antenna_tilt > 0 else 'up' if antenna_tilt < 0 else 'level'})")
        if antenna_tilt != 0:
            print(f"  Tilt direction: {antenna_tilt_azimuth}°")
        
        # CRITICAL DISCOVERY: SPLAT! looks for pattern files based on LRP FILENAME, not site name!
        # Pattern files MUST match the QTH/LRP filename base (lowercase "tx")
        create_pattern_files(
            antenna_type=antenna_type,
            azimuth_deg=antenna_azimuth,
            mechanical_tilt_deg=antenna_tilt,
            tilt_azimuth_deg=antenna_tilt_azimuth,
            output_dir=work_dir,
            site_name="tx"
        )
    
    def _run_splat(self, work_dir: Path, radius_km: float, rx_sensitivity_dbm: float):
        """
        Execute SPLAT! binary for ITM (Irregular Terrain Model) propagation analysis.
        
        CRITICAL: We use -L (not -c) to enable full RF propagation modeling with:
        - Frequency-dependent path loss
        - Antenna gain (via ERP in LRP file)
        - Longley-Rice ITM propagation model
        - Terrain diffraction and atmospheric effects
        
        The -c flag only does line-of-sight (viewshed) and ignores all RF parameters!
        """
        cmd = [
            str(self.splat_binary),
            "-t", "tx.qth",
            "-L", "2.0",  # ITM coverage analysis with RX at 2m AGL (ground level receivers)
            "-dbm",       # Output received power in dBm (not field strength)
            "-sc",        # Smooth contour interpolation — gives continuous color
                          # gradients instead of 10 dB stepped bands, enabling
                          # the frontend to resolve sub-10 dB directional diffs.
            "-m", "1.333",  # Four-thirds earth radius for atmospheric bending
            "-metric",
            "-R", str(radius_km),
            "-db", str(rx_sensitivity_dbm),  # Threshold for coverage contours
            "-ngs",
            "-N",
            "-o", "output.ppm",
            "-kml"
        ]
        
        logger.info(f"Running SPLAT! command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True
        )
        
        print(f"SPLAT! stdout: {result.stdout}")
        print(f"SPLAT! stderr: {result.stderr}")
        logger.info(f"SPLAT! stdout: {result.stdout}")
        logger.info(f"SPLAT! stderr: {result.stderr}")
        
        # Check for SDF loading issues in output
        if "SDF" in result.stdout or "sdf" in result.stdout.lower():
            print(f"DEBUG: SPLAT! SDF-related output detected")
        if "not found" in result.stderr.lower() or "error" in result.stderr.lower():
            print(f"WARNING: SPLAT! may have errors: {result.stderr}")
        
        if result.returncode != 0:
            logger.error(f"SPLAT! failed with return code {result.returncode}")
            logger.error(f"SPLAT! stderr: {result.stderr}")
            raise RuntimeError(f"SPLAT! execution failed: {result.stderr}")
        
        # Check if output files were created
        if not (work_dir / "output.ppm").exists():
            raise RuntimeError("SPLAT! did not create output.ppm file")
        if not (work_dir / "output.kml").exists():
            raise RuntimeError("SPLAT! did not create output.kml file")
        
        logger.info("SPLAT! execution successful")
    
    def _parse_splat_output(
        self,
        ppm_path: Path,
        kml_path: Path,
        tx_lat: float,
        tx_lon: float,
        tx_elev_m: float,
        frequency_mhz: float,
        tx_power_dbm: float,
        antenna_gain_dbi: float,
        antenna_type: str,
        antenna_azimuth: float,
        antenna_tilt: float = 0.0,
        antenna_tilt_azimuth: float = 0.0,
        analysis_radius_km: float = None
    ) -> Dict:
        """Parse SPLAT! PPM and KML output into coverage data"""
        # Parse KML for bounds
        tree = ET.parse(kml_path)
        namespace = {"kml": "http://earth.google.com/kml/2.1"}
        box = tree.find(".//kml:LatLonBox", namespace)
        
        north = float(box.find("kml:north", namespace).text)
        south = float(box.find("kml:south", namespace).text)
        east = float(box.find("kml:east", namespace).text)
        west = float(box.find("kml:west", namespace).text)
        
        print(f"KML bounds from SPLAT!:")
        print(f"  North: {north}")
        print(f"  South: {south}")
        print(f"  East: {east}")
        print(f"  West: {west}")
        print(f"  TX should be at: {tx_lat}, {tx_lon}")
        
        # Read PPM image
        with Image.open(ppm_path) as img:
            print(f"PPM image mode: {img.mode}, size: {img.size}")
            logger.info(f"PPM image mode: {img.mode}, size: {img.size}")
            
            # CRITICAL: Ensure we have an RGB image for color-based coverage detection
            # SPLAT! with -L -dbm flag outputs RGB PPM with colored signal strength contours
            if img.mode != 'RGB':
                print(f"WARNING: PPM is {img.mode}, converting to RGB")
                img = img.convert('RGB')
            
            img_array = np.array(img)
        
        print(f"PPM image shape: {img_array.shape}")
        logger.info(f"PPM image shape: {img_array.shape}")
        
        # Debug: show actual color distribution
        if len(img_array.shape) == 3:
            # Sample some pixels to see what colors we have
            unique_colors = set()
            for i in range(0, img_array.shape[0], 100):
                for j in range(0, img_array.shape[1], 100):
                    r, g, b = img_array[i, j]
                    if (r, g, b) != (255, 255, 255) and (r, g, b) != (128, 128, 128):
                        unique_colors.add((r, g, b))
            print(f"DEBUG: Non-background colors found (sample): {list(unique_colors)[:20]}")
        else:
            print(f"WARNING: Image is 2D (grayscale), shape: {img_array.shape}")
        
        # Extract RGB channels
        if len(img_array.shape) == 3:
            r = img_array[:, :, 0]
            g = img_array[:, :, 1]
            b = img_array[:, :, 2]
            
            # SPLAT! -dbm mode uses colored contours for signal strength.
            # With the -ngs flag, non-signal pixels are white (255,255,255).
            # SPLAT! also emits black (0,0,0) for pixels outside DEM coverage
            # ("should never get here" in WritePPMDBM).  Without -ngs it can
            # also write gray terrain or blue sea-level, so we filter broadly.
            is_background = (
                ((r == 255) & (g == 255) & (b == 255)) |             # white
                ((r == g) & (g == b) & (r > 100)) |                  # any gray > 100
                ((r == 0) & (g == 0) & (b == 0)) |                   # black (no DEM data)
                ((r == g) & (g == b) & (r < 10)) |                   # near-black
                ((r == 0) & (g == 0) & (b == 170))                   # sea-level blue
            )
            
            coverage_mask = ~is_background
            
            print(f"Coverage pixels: {np.sum(coverage_mask)} out of {coverage_mask.size}")
            logger.info(f"Coverage pixels: {np.sum(coverage_mask)}")
            
            # SPLAT! dBm color definitions (from splat.txt documentation)
            splat_colors = [
                (255, 0, 0, 0),           # Red = 0 dBm
                (255, 128, 0, -10),       # Orange-red = -10 dBm
                (255, 165, 0, -20),       # Orange = -20 dBm
                (255, 206, 0, -30),       # Yellow-orange = -30 dBm
                (255, 255, 0, -40),       # Yellow = -40 dBm
                (184, 255, 0, -50),       # Yellow-green = -50 dBm
                (0, 255, 0, -60),         # Green = -60 dBm
                (0, 208, 0, -70),         # Dark green = -70 dBm
                (0, 196, 196, -80),       # Cyan = -80 dBm
                (0, 148, 255, -90),       # Sky blue = -90 dBm
                (80, 80, 255, -100),      # Blue = -100 dBm
                (0, 38, 255, -110),       # Dark blue = -110 dBm
                (142, 63, 255, -120),     # Purple = -120 dBm
                (196, 54, 255, -130),     # Magenta = -130 dBm
                (255, 0, 255, -140),      # Bright magenta = -140 dBm
                (255, 194, 204, -150),    # Pink = -150 dBm
            ]
            
            # Maximum squared RGB distance to accept a color as a valid
            # SPLAT! signal color.  Anything farther is treated as a
            # non-signal artifact (terrain bleed, rendering glitch, etc.).
            MAX_COLOR_DIST_SQ = 15000
            
            # Pre-compute color array for vectorized distance calculation
            splat_rgb = np.array([(cr, cg, cb) for cr, cg, cb, _ in splat_colors], dtype=np.float32)
            splat_dbm = np.array([dbm for _, _, _, dbm in splat_colors], dtype=np.float64)
            
            signal_strength = np.full(img_array.shape[:2], -200.0)
            
            # Vectorized color -> dBm mapping over covered pixels only.
            # The previous per-pixel Python loop took minutes on large
            # SPLAT! outputs; NumPy broadcasting does the same work in
            # well under a second. Processing happens in chunks so the
            # (N_pixels x N_colors) distance matrix stays memory-bounded.
            cov_rows, cov_cols = np.nonzero(coverage_mask)
            rejected_pixels = 0
            CHUNK = 500_000
            for start in range(0, cov_rows.size, CHUNK):
                rows_c = cov_rows[start:start + CHUNK]
                cols_c = cov_cols[start:start + CHUNK]
                px = img_array[rows_c, cols_c, :3].astype(np.float32)
                
                # Squared RGB distance from each pixel to each reference color
                dists = ((px[:, None, :] - splat_rgb[None, :, :]) ** 2).sum(axis=2)
                i1 = np.argmin(dists, axis=1)
                d1 = dists[np.arange(i1.size), i1]
                
                # Reject anything too far from every SPLAT! signal color
                # (terrain bleed, rendering artifacts, etc.)
                invalid = d1 > MAX_COLOR_DIST_SQ
                rejected_pixels += int(invalid.sum())
                coverage_mask[rows_c[invalid], cols_c[invalid]] = False
                
                # With smooth contours (-sc), SPLAT! interpolates colors
                # between adjacent bands. Recover the actual dBm by
                # inverse-distance weighting the two closest reference
                # colors; exact matches take the band value directly.
                dists[np.arange(i1.size), i1] = np.inf
                i2 = np.argmin(dists, axis=1)
                d2 = dists[np.arange(i2.size), i2]
                w1 = 1.0 / np.maximum(d1, 1e-9)
                w2 = 1.0 / np.maximum(d2, 1e-9)
                interp = (splat_dbm[i1] * w1 + splat_dbm[i2] * w2) / (w1 + w2)
                values = np.where(d1 == 0, splat_dbm[i1], interp)
                
                valid = ~invalid
                signal_strength[rows_c[valid], cols_c[valid]] = values[valid]
            
            if rejected_pixels > 0:
                print(f"Rejected {rejected_pixels} pixels with unrecognized colors")
                logger.info(f"Rejected {rejected_pixels} pixels with unrecognized colors")
        else:
            # Grayscale fallback
            coverage_mask = img_array < 200
            signal_strength = np.where(coverage_mask, -80.0, -200.0)
            print(f"Grayscale image - coverage pixels: {np.sum(coverage_mask)}")
            logger.info(f"Grayscale image - coverage pixels: {np.sum(coverage_mask)}")
        
        # Crop and recalculate bounds based on analysis radius
        # SPLAT! generates a large area, but we only want to show the portion within our radius
        if analysis_radius_km:
            height, width = coverage_mask.shape
            
            # Calculate pixel coordinates of transmitter in SPLAT!'s image
            tx_col = int((tx_lon - west) / (east - west) * width)
            tx_row = int((north - tx_lat) / (north - south) * height)
            
            print(f"TX pixel position in {width}x{height} image:")
            print(f"  TX at ({tx_lat}, {tx_lon})")
            print(f"  Bounds: W={west}, E={east}, S={south}, N={north}")
            print(f"  TX pixel: row={tx_row}, col={tx_col}")
            
            # Calculate how many pixels correspond to the analysis radius
            # Approximate: degrees per km at this latitude
            km_per_deg_lat = 111.0
            km_per_deg_lon = 111.0 * math.cos(math.radians(tx_lat))
            
            # Pixels per degree
            pixels_per_deg_lon = width / (east - west)
            pixels_per_deg_lat = height / (north - south)
            
            # Radius in pixels
            radius_pixels_lon = analysis_radius_km * pixels_per_deg_lon / km_per_deg_lon
            radius_pixels_lat = analysis_radius_km * pixels_per_deg_lat / km_per_deg_lat
            radius_pixels = int(max(radius_pixels_lon, radius_pixels_lat) * 1.1)  # 10% buffer
            
            print(f"Cropping to {analysis_radius_km} km radius ({radius_pixels} pixels)")
            
            # Calculate crop bounds
            row_min = max(0, tx_row - radius_pixels)
            row_max = min(height, tx_row + radius_pixels)
            col_min = max(0, tx_col - radius_pixels)
            col_max = min(width, tx_col + radius_pixels)
            
            # Crop the arrays
            coverage_mask = coverage_mask[row_min:row_max, col_min:col_max]
            signal_strength = signal_strength[row_min:row_max, col_min:col_max]
            
            # Recalculate geographic bounds for the cropped region
            new_north = north - (row_min / height) * (north - south)
            new_south = north - (row_max / height) * (north - south)
            new_west = west + (col_min / width) * (east - west)
            new_east = west + (col_max / width) * (east - west)
            
            print(f"Cropped from {width}x{height} to {coverage_mask.shape[1]}x{coverage_mask.shape[0]}")
            print(f"New bounds: W={new_west:.6f}, E={new_east:.6f}, S={new_south:.6f}, N={new_north:.6f}")
            
            # Update bounds to the cropped region
            west, east, south, north = new_west, new_east, new_south, new_north
            
            # Now mask by actual distance (circular, not square crop).
            # Vectorized haversine over the whole grid — the previous
            # per-pixel Python loop dominated post-processing time.
            height, width = coverage_mask.shape
            
            pixel_lats = np.radians(north - (np.arange(height) / height) * (north - south))
            pixel_lons = np.radians(west + (np.arange(width) / width) * (east - west))
            tx_lat_rad = math.radians(tx_lat)
            tx_lon_rad = math.radians(tx_lon)
            
            dlat = pixel_lats[:, None] - tx_lat_rad          # (H, 1)
            dlon = pixel_lons[None, :] - tx_lon_rad          # (1, W)
            a = (np.sin(dlat / 2) ** 2
                 + math.cos(tx_lat_rad) * np.cos(pixel_lats)[:, None] * np.sin(dlon / 2) ** 2)
            distance_km = 6371 * 2 * np.arcsin(np.sqrt(a))   # (H, W) via broadcasting
            
            outside = distance_km > analysis_radius_km
            coverage_mask[outside] = False
            signal_strength[outside] = -200.0
            
            print(f"Masked coverage beyond {analysis_radius_km} km radius")
        
        # CRITICAL: Use the ACTUAL bounds from SPLAT!'s KML, not our calculated DEM bounds
        # SPLAT! determines its own map area based on terrain data availability
        print(f"Using SPLAT!'s KML bounds for image overlay")
        
        return {
            'coverage_mask': coverage_mask.tolist(),
            'signal_strength': signal_strength.tolist(),
            'tx_lat': tx_lat,
            'tx_lon': tx_lon,
            'tx_elev_m': tx_elev_m,
            'frequency_mhz': frequency_mhz,
            'tx_power_dbm': tx_power_dbm,
            'antenna_gain_dbi': antenna_gain_dbi,
            'antenna_type': antenna_type,
            'antenna_azimuth': antenna_azimuth,
            'antenna_tilt': antenna_tilt,
            'antenna_tilt_azimuth': antenna_tilt_azimuth,
            'dem_bounds': [west, south, east, north]
        }

