#!/usr/bin/env python3
"""
Live end-to-end smoke test for the MeshRF Coverage app.

Means and method
----------------
This script exercises the full request path of a RUNNING server — real
HTTP, real SPLAT! subprocess, real SRTM terrain data — rather than
mocking any layer. It verifies the complete lifecycle of a coverage
layer: calculate -> poll -> fetch -> export -> re-import -> cache hit.

Steps:
 1. Health check        GET  /api/health
 2. Start calculation   POST /api/coverage/single   (Reno NV area, so the
                        SRTM tiles in splat_cache/ are reused; the site
                        latitude is jittered per-run to force a fresh
                        SPLAT! calculation rather than a cache hit)
 3. Poll for progress   GET  /api/coverage/{id}/status  — distinct
                        progress values while SPLAT! runs prove the
                        event loop is NOT blocked by the calculation
                        (the asyncio.to_thread fix)
 4. Fetch result        GET  /api/coverage/{id}     — sanity-check grid
                        shape, coverage stats, and metadata echo
 5. Export              GET  /api/coverage/{id}/export/kmz and
                        GET  /api/coverage/{id}/export/geotiff
 6. Re-import both      POST /api/coverage/import   — verify both
                        round-trips recover bounds/metadata/coverage.
                        Both formats store the stepped SPLAT! color
                        scale, so recovered dBm values are quantized to
                        10 dB bands (band floors) rather than lossless.
 6b. Terrain view       GET  /api/coverage/{id}/hillshade — must return a
                        PNG rendered from the local DEM cache; and
                        GET  /api/peaks — must return a JSON peak list
                        (empty tolerated: Overpass may be unreachable)
 7. Cache hit           POST the identical request again — must complete
                        near-instantly with from_cache=True

Usage:
    # Terminal 1: start the server
    python -m uvicorn app:app --host 127.0.0.1 --port 8011
    # Terminal 2: run the test
    python smoke_test.py [--base-url http://127.0.0.1:8011]

Exits 0 on success, 1 on any failure.
"""

import argparse
import io
import sys
import time
import zipfile

import numpy as np
import requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8011')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')

    failures = []

    def check(label: str, ok: bool, detail: str = ''):
        status = 'PASS' if ok else 'FAIL'
        print(f"[{status}] {label}" + (f" — {detail}" if detail else ''))
        if not ok:
            failures.append(label)

    # ---- 1. Health check -------------------------------------------------
    r = requests.get(f"{base}/api/health", timeout=10)
    check('health endpoint', r.status_code == 200 and r.json().get('status') == 'healthy',
          f"HTTP {r.status_code}")

    # ---- 2. Start a fresh single-site calculation ------------------------
    # Jitter the latitude so the cache key differs on every run; the cache
    # key is built from site parameters, so a fixed location would be a
    # cache hit after the first run and skip SPLAT! entirely.
    jitter = (int(time.time()) % 1000) * 1e-5
    site = {
        'lat': 39.53 + jitter,
        'lon': -119.81,
        'elev_m': 10.0,
        'frequency_mhz': 905.0,
        'tx_power_dbm': 30.0,
        'antenna_gain_dbi': 8.0,
        'antenna_type': 'yagi_5el',
        'antenna_azimuth': 90.0,
        'antenna_tilt': 0.0,
        'antenna_tilt_azimuth': 0.0,
        'rx_sensitivity_dbm': -110.0,
        'max_range_km': 10.0,
        'site_name': 'SmokeTest',
    }
    r = requests.post(f"{base}/api/coverage/single", json=site, timeout=30)
    check('start calculation', r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        print('Cannot continue without a coverage id.')
        return 1
    coverage_id = r.json()['coverage_id']
    print(f"       coverage_id = {coverage_id}")

    # ---- 3. Poll status; distinct progress values prove a live event loop -
    t0 = time.time()
    seen_progress = []
    status = None
    while time.time() - t0 < 300:
        r = requests.get(f"{base}/api/coverage/{coverage_id}/status", timeout=10)
        body = r.json()
        status = body.get('status')
        prog = body.get('progress')
        if not seen_progress or seen_progress[-1] != prog:
            seen_progress.append(prog)
        if status in ('complete', 'error'):
            break
        time.sleep(1)
    elapsed = time.time() - t0
    check('calculation completes', status == 'complete',
          f"status={status} in {elapsed:.1f}s")
    check('progress updates while calculating (event loop responsive)',
          len(seen_progress) >= 2, f"progress values seen: {seen_progress}")

    # ---- 4. Fetch full coverage result ------------------------------------
    r = requests.get(f"{base}/api/coverage/{coverage_id}", timeout=60)
    data = r.json()
    mask = np.array(data['coverage_mask'])
    sig = np.array(data['signal_strength'])
    covered = int(mask.sum())
    check('coverage grid returned', mask.ndim == 2 and mask.shape == sig.shape,
          f"grid {mask.shape}, covered pixels: {covered}")
    check('nonzero coverage', covered > 0)
    check('signal values physical',
          bool((sig[mask] <= 30).all() and (sig[mask] >= -200).all()),
          f"range {sig[mask].min():.0f}..{sig[mask].max():.0f} dBm" if covered else 'no pixels')
    check('metadata echoed', data.get('antenna_type') == 'yagi_5el'
          and data.get('frequency_mhz') == 905.0)

    # ---- 5. Export KMZ and GeoTIFF -----------------------------------------
    r = requests.get(f"{base}/api/coverage/{coverage_id}/export/kmz", timeout=60)
    kmz_bytes = r.content
    kmz_ok = r.status_code == 200 and zipfile.is_zipfile(io.BytesIO(kmz_bytes))
    check('KMZ export', kmz_ok, f"{len(kmz_bytes)} bytes")

    r = requests.get(f"{base}/api/coverage/{coverage_id}/export/geotiff", timeout=60)
    tif_bytes = r.content
    check('GeoTIFF export', r.status_code == 200 and tif_bytes[:4] in (b'II*\x00', b'MM\x00*'),
          f"{len(tif_bytes)} bytes")

    # ---- 6. Re-import both exports -----------------------------------------
    r = requests.post(f"{base}/api/coverage/import",
                      files={'file': ('smoke.kmz', kmz_bytes, 'application/vnd.google-earth.kmz')},
                      timeout=120)
    imp = r.json() if r.status_code == 200 else {}
    imp_mask = np.array(imp.get('coverage_mask', [])) if imp else np.array([])
    check('KMZ import', r.status_code == 200 and imp.get('status') == 'complete',
          f"HTTP {r.status_code}")
    if imp:
        # KMZ import is lossy (10 dB color bands) but coverage footprint and
        # metadata must survive the round trip.
        check('KMZ round-trip footprint',
              imp_mask.shape == mask.shape and
              abs(int(imp_mask.sum()) - covered) / max(covered, 1) < 0.05,
              f"imported covered: {int(imp_mask.sum())} vs original {covered}")
        check('KMZ round-trip metadata',
              imp.get('site_name') == 'SmokeTest'
              and imp.get('frequency_mhz') == 905.0
              and imp.get('antenna_type') == 'yagi_5el'
              and abs(imp.get('tx_lat', 0) - site['lat']) < 1e-4)

    r = requests.post(f"{base}/api/coverage/import",
                      files={'file': ('smoke.tif', tif_bytes, 'image/tiff')},
                      timeout=120)
    imp2 = r.json() if r.status_code == 200 else {}
    check('GeoTIFF import', r.status_code == 200 and imp2.get('status') == 'complete',
          f"HTTP {r.status_code}")
    if imp2:
        sig2 = np.array(imp2['signal_strength'])
        mask2 = np.array(imp2['coverage_mask'])
        # The GeoTIFF now stores the stepped SPLAT! color scale (so the
        # file displays correctly in ordinary image viewers), which makes
        # the round trip banded like KMZ: the coverage footprint must
        # survive intact and every recovered value must be the 10 dB band
        # floor of the original (0 <= original - imported < 10 dB).
        footprint_ok = (mask2.shape == mask.shape and
                        abs(int(mask2.sum()) - covered) / max(covered, 1) < 0.05)
        check('GeoTIFF round-trip footprint', footprint_ok,
              f"imported covered: {int(mask2.sum())} vs original {covered}")
        if footprint_ok:
            both = mask2 & mask
            diffs = sig[both] - sig2[both]
            banded = bool(both.any() and (diffs >= -1e-6).all()
                          and (diffs < 10 + 1e-6).all())
            check('GeoTIFF round-trip within 10 dB bands', banded,
                  f"diff range {diffs.min():.2f}..{diffs.max():.2f} dB"
                  if both.any() else 'no overlapping pixels')
        # Metadata rides in raster tags and must survive the round trip
        # (bounds come from the georeferencing; TX location is not stored
        # in a GeoTIFF, so it is not checked here).
        check('GeoTIFF round-trip metadata',
              imp2.get('site_name') == 'SmokeTest'
              and imp2.get('frequency_mhz') == 905.0
              and imp2.get('antenna_type') == 'yagi_5el')

    # ---- 6b. Terrain view endpoints ------------------------------------------
    # Hillshade must render from the DEM tile the calculation just cached;
    # a PNG signature proves the full DEM-load -> shade -> encode path ran.
    r = requests.get(f"{base}/api/coverage/{coverage_id}/hillshade", timeout=120)
    check('hillshade endpoint',
          r.status_code == 200 and r.content[:8] == b'\x89PNG\r\n\x1a\n',
          f"HTTP {r.status_code}, {len(r.content)} bytes")

    # Peaks endpoint must answer with a JSON list. An EMPTY list passes:
    # the Overpass API is an external service and its availability must
    # not fail the smoke test — the endpoint contract is "never errors".
    w, s, e, n = data['dem_bounds']
    r = requests.get(f"{base}/api/peaks",
                     params={'west': w, 'south': s, 'east': e, 'north': n},
                     timeout=90)
    peaks_body = r.json() if r.status_code == 200 else {}
    check('peaks endpoint',
          r.status_code == 200 and isinstance(peaks_body.get('peaks'), list),
          f"HTTP {r.status_code}, {len(peaks_body.get('peaks', []))} peaks"
          + (', cached' if peaks_body.get('cached') else ''))

    # ---- 7. Identical request again must be a cache hit ---------------------
    r = requests.post(f"{base}/api/coverage/single", json=site, timeout=30)
    cid2 = r.json()['coverage_id']
    t0 = time.time()
    from_cache = False
    while time.time() - t0 < 30:
        body = requests.get(f"{base}/api/coverage/{cid2}/status", timeout=10).json()
        if body.get('status') == 'complete':
            from_cache = requests.get(f"{base}/api/coverage/{cid2}",
                                      timeout=60).json().get('from_cache', False)
            break
        time.sleep(0.5)
    check('repeat request served from cache', from_cache,
          f"completed in {time.time() - t0:.1f}s")

    # ---- Summary -------------------------------------------------------------
    print()
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} failing check(s): {failures}")
        return 1
    print("SMOKE TEST PASSED — all checks green")
    return 0


if __name__ == '__main__':
    sys.exit(main())
