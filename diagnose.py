#!/usr/bin/env python3
"""
Diagnostic script to check if SPLAT! parameters are working correctly.
Run this to verify the fixes are in place.
"""

import sys
from pathlib import Path

print("=" * 80)
print("SPLAT! PARAMETER DIAGNOSTIC")
print("=" * 80)

# Check 1: Verify splat_service.py has -L flag
print("\n1. Checking SPLAT! command mode...")
splat_service_path = Path("src/splat_service.py")
if splat_service_path.exists():
    content = splat_service_path.read_text()
    if '"-L", "2.0"' in content:
        print("   ✓ CORRECT: Using -L (ITM mode)")
    elif '"-c", "2.0"' in content:
        print("   ✗ WRONG: Still using -c (LOS mode) - parameters will be ignored!")
        sys.exit(1)
    else:
        print("   ? UNKNOWN: Cannot find SPLAT! mode flag")
    
    if '"-dbm"' in content:
        print("   ✓ CORRECT: Using -dbm flag for signal strength")
    else:
        print("   ✗ MISSING: -dbm flag not found")
else:
    print("   ✗ ERROR: splat_service.py not found")
    sys.exit(1)

# Check 2: Verify cache key includes antenna parameters
print("\n2. Checking cache key...")
app_path = Path("app.py")
if app_path.exists():
    content = app_path.read_text()
    if 'antenna_type: str = "omnidirectional", antenna_azimuth: float = 0.0) -> str:' in content:
        print("   ✓ CORRECT: Cache key includes antenna_type and antenna_azimuth")
    else:
        print("   ✗ WRONG: Cache key missing antenna parameters - changes won't trigger recalculation!")
        sys.exit(1)
    
    # Check the return statement
    if 'antenna_type}_{antenna_azimuth:.1f}' in content:
        print("   ✓ CORRECT: Cache key returns antenna_type and antenna_azimuth")
    else:
        print("   ✗ WRONG: Cache key doesn't include antenna parameters in return value!")
        sys.exit(1)
else:
    print("   ✗ ERROR: app.py not found")
    sys.exit(1)

# Check 3: Verify cache is clear or minimal
print("\n3. Checking cache database...")
try:
    import sqlite3
    db_path = Path("coverage_db/coverage_cache.db")
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM site_coverage')
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            print(f"   ✓ GOOD: Cache is empty ({count} entries)")
        elif count < 5:
            print(f"   ⚠ OK: Cache has {count} entries (should be fresh calculations)")
        else:
            print(f"   ⚠ WARNING: Cache has {count} entries")
            print(f"      Consider clearing with: python3 -c \"import sqlite3; conn = sqlite3.connect('coverage_db/coverage_cache.db'); conn.execute('DELETE FROM site_coverage'); conn.commit()\"")
    else:
        print("   ✓ GOOD: No cache database yet")
except Exception as e:
    print(f"   ? Cannot check cache: {e}")

# Check 4: Verify antenna gain is passed through
print("\n4. Checking antenna gain parameter flow...")
if 'antenna_gain_dbi=self.antenna_gain_dbi' in Path("src/coverage_calculator.py").read_text():
    print("   ✓ CORRECT: coverage_calculator passes antenna_gain_dbi to SPLAT!")
else:
    print("   ✗ WRONG: coverage_calculator not passing antenna_gain_dbi")

if 'antenna_gain_dbi: float = 0.0,' in splat_service_path.read_text():
    print("   ✓ CORRECT: splat_service accepts antenna_gain_dbi parameter")
else:
    print("   ✗ WRONG: splat_service doesn't accept antenna_gain_dbi")

# Check 5: Verify LRP file creation includes antenna gain
if 'tx_power_dbm + antenna_gain_dbi' in splat_service_path.read_text():
    print("   ✓ CORRECT: LRP file ERP calculation includes antenna_gain_dbi")
else:
    print("   ✗ WRONG: LRP file not using antenna_gain_dbi in ERP calculation")

# Check 6: Test ERP calculation
print("\n5. Testing ERP calculation...")
print("   Example: 50W (47 dBm) with 6 dBi antenna:")
tx_power_dbm = 47.0
antenna_gain_dbi = 6.0
system_loss_db = 0.0
erp_watts = 10 ** ((tx_power_dbm + antenna_gain_dbi - system_loss_db - 30) / 10)
print(f"   ERP = 10^(({tx_power_dbm} + {antenna_gain_dbi} - {system_loss_db} - 30) / 10)")
print(f"   ERP = {erp_watts:.2f} watts")
print(f"   Expected: ~200 watts (4× the 50W input)")
if 190 < erp_watts < 210:
    print("   ✓ CORRECT: ERP calculation is working")
else:
    print("   ✗ WRONG: ERP calculation seems incorrect")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)

print("\n📋 NEXT STEPS:")
print("1. If all checks pass (✓), restart your web server:")
print("   - Stop the server (Ctrl+C)")
print("   - Start it again: python app.py")
print("\n2. Clear your browser cache or use incognito mode")
print("\n3. Try changing antenna gain from 0 to 6 dBi")
print("   - Should see DRAMATIC increase in coverage")
print("   - Coverage area should roughly quadruple")
print("\n4. Check server logs for:")
print("   - 'Running SPLAT! command:' should show '-L 2.0 -dbm'")
print("   - 'Calculated ERP:' should show different watts for different gains")
print("   - Should NOT see 'Using cached coverage' when parameters change")

print("\n" + "=" * 80)

