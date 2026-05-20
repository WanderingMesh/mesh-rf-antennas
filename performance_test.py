#!/usr/bin/env python3
"""
Performance test for the optimized Longley-Rice implementation
"""

import time
import numpy as np
import sys
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.splat_longley_rice import calculate_splat_coverage_map

def test_performance():
    """Test the performance of the optimized coverage calculation."""
    print("Testing optimized Longley-Rice performance...")
    
    # Create mock DEM data (smaller for faster testing)
    dem_data = np.random.uniform(1000, 2000, (200, 200))  # 200x200 array
    dem_transform = (0.001, 0, -120, 0, -0.001, 40)  # Mock transform
    
    # Test parameters
    tx_lat, tx_lon = 39.5296, -119.8138
    tx_elev_m = 1500.0
    frequency_mhz = 900.0
    tx_power_dbm = 30.0
    analysis_radius_km = 10.0  # Smaller radius for faster testing
    
    print(f"DEM size: {dem_data.shape}")
    print(f"Analysis radius: {analysis_radius_km} km")
    
    # Time the calculation
    start_time = time.time()
    
    coverage_data = calculate_splat_coverage_map(
        tx_lat=tx_lat,
        tx_lon=tx_lon,
        tx_elev_m=tx_elev_m,
        dem_data=dem_data,
        dem_transform=dem_transform,
        frequency_mhz=frequency_mhz,
        tx_power_dbm=tx_power_dbm,
        rx_sensitivity_dbm=-100.0,
        analysis_radius_km=analysis_radius_km,
        pixel_size_km=0.1
    )
    
    end_time = time.time()
    calculation_time = end_time - start_time
    
    # Convert back to numpy arrays for analysis
    coverage_mask = np.array(coverage_data['coverage_mask'], dtype=bool)
    signal_strength = np.array(coverage_data['signal_strength'], dtype=np.float32)
    
    # Results
    coverage_pixels = np.sum(coverage_mask)
    total_pixels = coverage_mask.size
    coverage_percentage = (coverage_pixels / total_pixels) * 100
    
    print(f"\nPerformance Results:")
    print(f"Calculation time: {calculation_time:.2f} seconds")
    print(f"Coverage pixels: {coverage_pixels:,}")
    print(f"Coverage percentage: {coverage_percentage:.1f}%")
    if coverage_pixels > 0:
        print(f"Signal strength range: {signal_strength[coverage_mask].min():.1f} to {signal_strength[coverage_mask].max():.1f} dBm")
    else:
        print("Signal strength range: No coverage detected")
    
    if calculation_time < 2.0:
        print("✓ Performance is good (< 2 seconds)")
    elif calculation_time < 5.0:
        print("⚠ Performance is acceptable (< 5 seconds)")
    else:
        print("❌ Performance is too slow (> 5 seconds)")
    
    return calculation_time

if __name__ == "__main__":
    test_performance()
