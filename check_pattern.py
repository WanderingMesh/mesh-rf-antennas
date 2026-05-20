#!/usr/bin/env python3
"""
Check if antenna pattern files are actually directional
"""

from src.antenna_patterns import generate_azimuth_pattern
import numpy as np

# Generate pattern for 11-element Yagi pointing East (90°)
pattern = generate_azimuth_pattern('yagi_11el', rotation_deg=90.0)
lines = pattern.split('\n')

print("=" * 80)
print("ANTENNA PATTERN CHECK - 11-Element Yagi @ 90° (East)")
print("=" * 80)

# Parse the pattern
rotation = lines[0]
print(f"\nRotation angle: {rotation}° (should be 90)")

vals = {}
for line in lines[1:]:
    if line.strip():
        parts = line.split()
        if len(parts) == 2:
            angle = int(parts[0])
            value = float(parts[1])
            vals[angle] = value

# Check key directions
print("\nPattern values (field strength, 0.0-1.0):")
print(f"  0° (North):     {vals.get(0, 0):.4f}")
print(f"  90° (East):     {vals.get(90, 0):.4f}  ← Should be STRONGEST")
print(f"  180° (South):   {vals.get(180, 0):.4f}")
print(f"  270° (West):    {vals.get(270, 0):.4f}  ← Should be WEAKEST")

# Calculate ratios
east_west_ratio = 20 * np.log10(vals.get(90, 1) / vals.get(270, 0.001))
print(f"\nEast/West Ratio: {east_west_ratio:.1f} dB (should be ~25 dB)")

# Check if pattern is actually directional
if vals.get(90, 0) > vals.get(270, 0) * 3:
    print("\n✓ Pattern IS directional (East > 3× West)")
else:
    print("\n✗ Pattern is NOT directional enough!")
    print(f"  Ratio: {vals.get(90, 0) / vals.get(270, 0.001):.2f}× (should be ~17×)")

# Show pattern every 45 degrees
print("\nPattern every 45°:")
for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
    value = vals.get(angle, 0)
    db = 20 * np.log10(value) if value > 0 else -999
    bar = '#' * int(value * 50)
    direction = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][angle // 45]
    print(f"  {angle:3d}° ({direction:2s}): {value:.4f} ({db:6.1f} dB) {bar}")

print("\n" + "=" * 80)
print("If pattern shows East (90°) much stronger than West (270°), pattern is correct.")
print("If SPLAT! output still looks omnidirectional, SPLAT! isn't using the patterns!")
print("=" * 80)



