#!/usr/bin/env python3
"""
Diagnostic script to examine raw SPLAT! output vs displayed data.
This saves intermediate files for manual inspection.
"""

import subprocess
import shutil
from pathlib import Path
from PIL import Image
import numpy as np

# Your problem location
TX_LAT = 39.589644
TX_LON = -119.929333
TX_HEIGHT = 3  # meters AGL

OUTPUT_DIR = Path("/tmp/splat_diagnostic")
OUTPUT_DIR.mkdir(exist_ok=True)

print("=" * 80)
print("SPLAT! DIAGNOSTIC - Checking raw output vs display")
print("=" * 80)
print(f"\nSite: {TX_LAT}, {TX_LON}")
print(f"Height: {TX_HEIGHT}m AGL")
print(f"Output directory: {OUTPUT_DIR}")

# Copy terrain files
print("\n1. Copying terrain data...")
splat_test = Path("splat_test")
for sdf in splat_test.glob("*.sdf"):
    shutil.copy(sdf, OUTPUT_DIR)
    print(f"   Copied {sdf.name}")

# Create QTH file
print("\n2. Creating QTH file...")
qth_path = OUTPUT_DIR / "tx.qth"
qth_content = f"""TX
{TX_LAT}
{abs(TX_LON)}
{TX_HEIGHT} meters
"""
qth_path.write_text(qth_content)
print(f"   {qth_path}")
print(qth_content)

# Create LRP file
print("\n3. Creating LRP file...")
lrp_path = OUTPUT_DIR / "tx.lrp"
lrp_content = """15.000
0.005000
301.000
907.000
5
1
0.50
0.50
10.0
"""
lrp_path.write_text(lrp_content)
print(f"   {lrp_path}")

# Run SPLAT!
print("\n4. Running SPLAT!...")
splat_binary = Path("splat_src/splat-1.4.2/splat").resolve()

cmd = [
    str(splat_binary),
    "-t", "tx.qth",
    "-L", "2.0",  # RX height
    "-dbm",
    "-m", "1.333",
    "-metric",
    "-R", "50",  # 50 km radius
    "-db", "-100",  # Threshold
    "-ngs",
    "-o", "output.ppm",
    "-kml"
]

print(f"   Command: {' '.join(cmd)}")
result = subprocess.run(cmd, cwd=OUTPUT_DIR, capture_output=True, text=True)

print("\n5. SPLAT! Output:")
print("-" * 40)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Check output files
print("\n6. Output files created:")
for f in OUTPUT_DIR.glob("*"):
    if f.is_file():
        print(f"   {f.name}: {f.stat().st_size:,} bytes")

# Analyze PPM
ppm_path = OUTPUT_DIR / "output.ppm"
if ppm_path.exists():
    print("\n7. Analyzing PPM output...")
    img = Image.open(ppm_path)
    arr = np.array(img)
    print(f"   Image size: {img.size}")
    print(f"   Image mode: {img.mode}")
    print(f"   Array shape: {arr.shape}")
    
    # Count coverage pixels
    if len(arr.shape) == 3:
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        
        # Background detection
        is_gray = (r == 128) & (g == 128) & (b == 128)
        is_white = (r == 255) & (g == 255) & (b == 255)
        is_background = is_gray | is_white
        
        coverage = ~is_background
        coverage_count = np.sum(coverage)
        total_pixels = coverage.size
        
        print(f"\n   Total pixels: {total_pixels:,}")
        print(f"   Coverage pixels: {coverage_count:,}")
        print(f"   Coverage %: {100*coverage_count/total_pixels:.2f}%")
        
        # Analyze by color
        print("\n   Coverage by color:")
        red_pixels = np.sum((r > 200) & (g < 100) & (b < 100))
        yellow_pixels = np.sum((r > 200) & (g > 150) & (b < 100))
        green_pixels = np.sum((g > 200) & (r < 150) & (b < 150))
        cyan_pixels = np.sum((g > 150) & (b > 150) & (r < 100))
        blue_pixels = np.sum((b > 200) & (r < 100) & (g < 100))
        
        print(f"   Red (strong):   {red_pixels:,}")
        print(f"   Yellow:         {yellow_pixels:,}")
        print(f"   Green:          {green_pixels:,}")
        print(f"   Cyan:           {cyan_pixels:,}")
        print(f"   Blue (weak):    {blue_pixels:,}")
        
        # Find where coverage exists
        coverage_rows, coverage_cols = np.where(coverage)
        if len(coverage_rows) > 0:
            print(f"\n   Coverage extent:")
            print(f"   Rows: {coverage_rows.min()} to {coverage_rows.max()}")
            print(f"   Cols: {coverage_cols.min()} to {coverage_cols.max()}")
            
            # Check quadrants (relative to center)
            center_row = arr.shape[0] // 2
            center_col = arr.shape[1] // 2
            
            ne = np.sum(coverage[:center_row, center_col:])
            nw = np.sum(coverage[:center_row, :center_col])
            se = np.sum(coverage[center_row:, center_col:])
            sw = np.sum(coverage[center_row:, :center_col])
            
            print(f"\n   Coverage by quadrant:")
            print(f"   NW: {nw:,} pixels")
            print(f"   NE: {ne:,} pixels")
            print(f"   SW: {sw:,} pixels")
            print(f"   SE: {se:,} pixels  <-- You expected coverage here!")
            
            if se < min(ne, nw, sw):
                print(f"\n   ⚠️  SE has LEAST coverage - confirms your observation!")
                print(f"   Either terrain is blocking, or SPLAT! terrain data is wrong.")
        
        # Save a converted PNG for easy viewing
        png_path = OUTPUT_DIR / "output.png"
        img.save(png_path)
        print(f"\n   Saved PNG: {png_path}")

# Parse KML bounds
kml_path = OUTPUT_DIR / "output.kml"
if kml_path.exists():
    print("\n8. KML bounds:")
    import xml.etree.ElementTree as ET
    tree = ET.parse(kml_path)
    ns = {"kml": "http://earth.google.com/kml/2.1"}
    box = tree.find(".//kml:LatLonBox", ns)
    if box is not None:
        north = box.find("kml:north", ns).text
        south = box.find("kml:south", ns).text
        east = box.find("kml:east", ns).text
        west = box.find("kml:west", ns).text
        print(f"   North: {north}")
        print(f"   South: {south}")
        print(f"   East:  {east}")
        print(f"   West:  {west}")

# Check site report
report_path = OUTPUT_DIR / "TX-site_report.txt"
if report_path.exists():
    print("\n9. Site Report:")
    print("-" * 40)
    try:
        report = report_path.read_text(encoding='latin-1')
        print(report)
    except:
        print("   Could not read report")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
print(f"\nFiles saved to: {OUTPUT_DIR}")
print(f"View the PNG: open {OUTPUT_DIR}/output.png")
print("\nThis shows the RAW SPLAT! output before any processing.")
print("If SE coverage is missing here, it's SPLAT!/terrain data issue.")
print("If SE coverage exists here but not in app, it's a display issue.")



