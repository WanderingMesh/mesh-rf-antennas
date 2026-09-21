#!/usr/bin/env python3
"""
Test script for Longley-Rice RF Coverage Web Application

This script tests the core functionality of the application without
requiring the full web server to be running.
"""

import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.splat_longley_rice import SPLATLongleyRice, calculate_splat_coverage_map
from src.dem_handler import DEMHandler, create_dem_bounds
from config import get_config

def test_longley_rice_model():
    """Test the SPLAT! compatible Longley-Rice model."""
    print("Testing SPLAT! compatible Longley-Rice model...")
    
    # Initialize model
    lr_model = SPLATLongleyRice(
        frequency_mhz=900.0,
        tx_power_dbm=30.0,
        tx_height_m=100.0
    )
    
    # Test path loss calculation
    distance_km = 10.0
    path_loss = lr_model.calculate_path_loss(distance_km)
    
    print(f"Path loss at {distance_km} km: {path_loss:.2f} dB")
    
    # Test received power calculation
    rx_power = lr_model.calculate_received_power(distance_km)
    print(f"Received power at {distance_km} km: {rx_power:.2f} dBm")
    
    # Test coverage viability
    is_viable = lr_model.is_coverage_viable(rx_power, -100.0, 3.0)
    print(f"Coverage viable: {is_viable}")
    
    print("✓ Longley-Rice model test passed\n")

def test_dem_handler():
    """Test the DEM handler."""
    print("Testing DEM handler...")
    
    # Initialize DEM handler
    dem_handler = DEMHandler(cache_dir="test_dem_cache", resolution=90)
    
    # Test bounds calculation
    bounds = create_dem_bounds(39.5296, -119.8138, 10.0)  # 10km radius around Reno
    print(f"DEM bounds: {bounds}")
    
    # Test coordinate conversion. rasterio requires a real Affine
    # transform — a bare tuple is misinterpreted as GCPs and raises.
    from rasterio.transform import Affine
    transform = Affine(0.001, 0, -120, 0, -0.001, 40)
    lat, lon = 39.5296, -119.8138
    row, col = dem_handler.latlon_to_pixel(lat, lon, transform)
    print(f"Pixel coordinates for ({lat}, {lon}): ({row}, {col})")
    
    # With this transform: col = (lon - west) / 0.001, row = (north - lat) / 0.001.
    # This also guards against the historical bug where row/col came back swapped.
    assert row == int((40 - lat) / 0.001), f"row {row} is wrong — row/col may be swapped"
    assert col == int((lon - (-120)) / 0.001), f"col {col} is wrong — row/col may be swapped"
    
    print("✓ DEM handler test passed\n")

def test_coverage_calculation():
    """Test coverage calculation with mock data."""
    print("Testing coverage calculation...")
    
    # Create mock DEM data
    import numpy as np
    dem_data = np.random.uniform(1000, 2000, (100, 100))  # 100x100 array with elevations 1000-2000m
    dem_transform = (0.001, 0, -120, 0, -0.001, 40)  # Mock transform
    
    # Test coverage calculation
    coverage_data = calculate_splat_coverage_map(
        tx_lat=39.5296,
        tx_lon=-119.8138,
        tx_elev_m=1500.0,
        dem_data=dem_data,
        dem_transform=dem_transform,
        frequency_mhz=900.0,
        tx_power_dbm=30.0,
        rx_sensitivity_dbm=-100.0,
        analysis_radius_km=5.0,
        pixel_size_km=0.1
    )
    
    # calculate_splat_coverage_map returns JSON-friendly nested lists;
    # convert back to arrays the same way coverage_calculator.py does.
    coverage_mask = np.array(coverage_data['coverage_mask'], dtype=bool)
    signal_strength = np.array(coverage_data['signal_strength'], dtype=np.float32)
    
    print(f"Coverage mask shape: {coverage_mask.shape}")
    print(f"Coverage pixels: {np.sum(coverage_mask)}")
    print(f"Signal strength range: {signal_strength.min():.1f} to {signal_strength.max():.1f} dBm")
    
    assert coverage_mask.shape == dem_data.shape
    assert signal_strength.shape == dem_data.shape
    
    print("✓ Coverage calculation test passed\n")

def test_lora_sensitivity_lookup():
    """Test the per-SF/chipset LoRa sensitivity resolver."""
    import pytest
    from src.lora_link_budget import resolve_sensitivity

    # Datasheet anchor points at 125 kHz
    assert resolve_sensitivity('sx1262', 7, 125.0) == -124.0
    assert resolve_sensitivity('sx1262', 12, 125.0) == -137.0
    assert resolve_sensitivity('sx1276', 12, 125.0) == -136.0

    # Bandwidth scaling: doubling BW costs ~3 dB, halving gains ~3 dB.
    # SF11/250 (Meshtastic LongFast on SX1262) and SF7/62.5 (MeshCore US).
    assert resolve_sensitivity('sx1262', 11, 250.0) == -132.5
    assert resolve_sensitivity('sx1262', 7, 62.5) == -127.0

    # LLCC68 restrictions: -129 dBm floor, limited SF per BW, no 62.5 kHz
    assert resolve_sensitivity('llcc68', 9, 125.0) == -129.0
    with pytest.raises(ValueError):
        resolve_sensitivity('llcc68', 10, 125.0)   # SF10 needs >= 250 kHz
    with pytest.raises(ValueError):
        resolve_sensitivity('llcc68', 7, 62.5)     # BW unsupported

    # Input validation
    with pytest.raises(ValueError):
        resolve_sensitivity('nrf905', 7, 125.0)    # unknown chipset
    with pytest.raises(ValueError):
        resolve_sensitivity('sx1262', 6, 125.0)    # SF out of range
    with pytest.raises(ValueError):
        resolve_sensitivity('sx1262', 7, 100.0)    # invalid bandwidth

    print("✓ LoRa sensitivity lookup test passed\n")

def test_configuration():
    """Test configuration loading."""
    print("Testing configuration...")
    
    config = get_config('default')
    print(f"RF frequency: {config['rf']['frequency_mhz']} MHz")
    print(f"TX power: {config['rf']['tx_power_dbm']} dBm")
    print(f"DEM resolution: {config['dem']['dem_resolution']} m")
    print(f"Analysis radius: {config['dem']['analysis_radius_km']} km")
    
    print("✓ Configuration test passed\n")

def main():
    """Run all tests."""
    print("="*60)
    print("LONGLEY-RICE RF COVERAGE APPLICATION - TEST SUITE")
    print("="*60)
    
    try:
        test_configuration()
        test_longley_rice_model()
        test_dem_handler()
        test_coverage_calculation()
        
        print("="*60)
        print("ALL TESTS PASSED! ✓")
        print("="*60)
        print("The application is ready to run.")
        print("Start the web server with: python app.py")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
