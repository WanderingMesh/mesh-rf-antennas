#!/usr/bin/env python3
"""
Test script to verify antenna patterns work with SPLAT!
"""

import subprocess
import tempfile
from pathlib import Path
from src.antenna_patterns import create_pattern_files

# Test parameters
test_lat = 39.572220
test_lon = -119.801898
test_elev_m = 25
test_freq = 900.0
test_power_dbm = 22.0
test_gain_dbi = 13.0  # 11-element Yagi gain
antenna_type = 'yagi_11el'
antenna_azimuth = 92.0

print("=" * 80)
print("MANUAL SPLAT! TEST WITH ANTENNA PATTERNS")
print("=" * 80)

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    print(f"\nWorking directory: {tmpdir}")
    
    # Create QTH file
    qth_file = tmpdir / "tx.qth"
    qth_content = f"""TX
{test_lat}
{-test_lon}
{test_elev_m} meters
"""
    qth_file.write_text(qth_content)
    print(f"\n✓ Created: {qth_file.name}")
    
    # Create LRP file
    lrp_file = tmpdir / "tx.lrp"
    erp_watts = 10 ** ((test_power_dbm + test_gain_dbi - 30) / 10)
    lrp_content = f"""15.000
0.005000
301.000
{test_freq:.3f}
5
1
0.50
0.50
{erp_watts:.2f}
"""
    lrp_file.write_text(lrp_content)
    print(f"✓ Created: {lrp_file.name}")
    print(f"  ERP: {erp_watts:.2f} watts ({test_power_dbm} dBm + {test_gain_dbi} dBi)")
    
    # Create antenna pattern files
    print(f"\n✓ Creating antenna pattern files...")
    az_path, el_path = create_pattern_files(
        antenna_type=antenna_type,
        azimuth_deg=antenna_azimuth,
        output_dir=tmpdir,
        site_name="tx"
    )
    
    # Verify files exist
    print(f"\n✓ Verifying files:")
    for fname in ['tx.qth', 'tx.lrp', 'tx.az', 'tx.el']:
        fpath = tmpdir / fname
        if fpath.exists():
            print(f"  ✓ {fname} exists ({fpath.stat().st_size} bytes)")
        else:
            print(f"  ✗ {fname} MISSING!")
    
    # Copy some terrain files for testing
    import shutil
    splat_test_dir = Path("splat_test")
    if splat_test_dir.exists():
        print(f"\n✓ Copying terrain files from {splat_test_dir}...")
        for sdf_file in splat_test_dir.glob("*.sdf"):
            shutil.copy(sdf_file, tmpdir)
            print(f"  ✓ Copied {sdf_file.name}")
    
    # Run SPLAT!
    splat_binary = Path("splat_src/splat-1.4.2/splat").resolve()
    cmd = [
        str(splat_binary),
        "-t", "tx.qth",
        "-L", "2.0",
        "-dbm",
        "-m", "1.333",
        "-metric",
        "-R", "50",
        "-db", "-100",
        "-ngs",
        "-N",
        "-o", "output.ppm",
        "-kml"
    ]
    
    print(f"\n" + "=" * 80)
    print("RUNNING SPLAT!")
    print("=" * 80)
    print(f"Command: {' '.join(cmd)}")
    print(f"Working dir: {tmpdir}")
    
    result = subprocess.run(
        cmd,
        cwd=tmpdir,
        capture_output=True,
        text=True
    )
    
    print(f"\n{'=' * 80}")
    print("SPLAT! OUTPUT")
    print("=" * 80)
    print(result.stdout)
    
    if result.stderr:
        print(f"\n{'=' * 80}")
        print("SPLAT! STDERR")
        print("=" * 80)
        print(result.stderr)
    
    print(f"\n{'=' * 80}")
    print("RESULT FILES")
    print("=" * 80)
    
    for fname in ['output.ppm', 'output.kml', 'TX-site_report.txt']:
        fpath = tmpdir / fname
        if fpath.exists():
            print(f"✓ {fname} created ({fpath.stat().st_size} bytes)")
        else:
            print(f"✗ {fname} NOT created")
    
    # Check site report for antenna pattern mention
    site_report = tmpdir / "TX-site_report.txt"
    if site_report.exists():
        print(f"\n{'=' * 80}")
        print("CHECKING SITE REPORT FOR ANTENNA PATTERN INFO")
        print("=" * 80)
        report_text = site_report.read_text()
        if "antenna" in report_text.lower() or "pattern" in report_text.lower():
            print("✓ Site report mentions antenna/pattern")
            for line in report_text.split('\n'):
                if 'antenna' in line.lower() or 'pattern' in line.lower():
                    print(f"  {line}")
        else:
            print("✗ Site report does NOT mention antenna patterns!")
            print("\nFirst 50 lines of report:")
            print('\n'.join(report_text.split('\n')[:50]))
    
    print(f"\n{'=' * 80}")
    print("TEST COMPLETE")
    print("=" * 80)
    print(f"\nFiles remain in: {tmpdir}")
    print("Press Enter to clean up and exit...")
    input()



