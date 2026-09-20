# Testing Strategy

## Test layers

| Layer | File | Runner | What it covers |
|---|---|---|---|
| Unit / integration | `test_app.py` | `pytest test_app.py` | Antenna patterns, DEM handler coordinate math, coverage calculation structure, export round-trip helpers (mocked/synthetic data, no live server) |
| Live end-to-end smoke | `smoke_test.py` | See below | Full HTTP lifecycle against a running server with the real SPLAT! binary and real SRTM terrain |
| Manual diagnostics | `test_antenna_pattern.py` | run directly, NOT via pytest | SPLAT! pattern-file plumbing; writes PPM output for eyeball inspection |

## Live end-to-end smoke test — means and method

`smoke_test.py` is the authoritative record of the method; this section
summarizes it.

### Means (test rig)

- **Server**: the actual FastAPI app served by uvicorn on a dedicated port
  (8011 by default, to avoid colliding with a dev instance on 8000/8001):
  `python -m uvicorn app:app --host 127.0.0.1 --port 8011`
- **Client**: `smoke_test.py`, a plain `requests`-based script — real HTTP
  over the loopback interface, no test client shortcuts, no mocks.
- **Terrain**: real SRTM tiles. The test site is in the Reno, NV area
  (39.53, −119.81) so the SDF tiles already in `splat_cache/` are reused
  and the run does not depend on network downloads.
- **Propagation**: the locally built SPLAT! 1.4.2 binary
  (`splat_src/splat-1.4.2/splat`), invoked by the server exactly as in
  production use.

### Method (checks, in order)

1. **Health** — `GET /api/health` returns `status: healthy`.
2. **Fresh calculation** — `POST /api/coverage/single` with a 5-element
   Yagi at azimuth 90°, 905 MHz, 30 dBm, 10 km radius. The latitude is
   jittered per-run (epoch-seconds based) so the SQLite cache key never
   matches a previous run — this guarantees SPLAT! actually executes.
3. **Event-loop responsiveness** — the status endpoint is polled once per
   second during the calculation; observing ≥ 2 distinct progress values
   proves the server keeps serving requests while SPLAT! runs (validates
   the `asyncio.to_thread` offloading). Typical sequence: 5 → 20 → 40 →
   80 → 100.
4. **Result sanity** — grid is 2-D with matching mask/signal shapes,
   nonzero covered pixels, all covered signal values within physical
   bounds (−200 … +30 dBm), request metadata echoed back.
5. **Export** — KMZ (must be a valid zip) and GeoTIFF (must carry a TIFF
   magic number) both download successfully.
6. **Import round-trip** — both exports are re-uploaded through
   `POST /api/coverage/import`:
   - KMZ: lossy by design (10 dB color bands), so the check is that the
     coverage footprint matches within 5 % and site metadata (name,
     frequency, antenna type, TX location) survives the KML round trip.
   - GeoTIFF: lossless by design (raw dBm in band 1, metadata in raster
     tags), so every covered pixel must match the original signal values
     and the mask must be identical.
7. **Cache** — the identical calculation request is repeated; it must
   complete quickly and report `from_cache: true` (SQLite coverage cache).

### Latest results (2026-08-10, dev/0.20.0)

All 16 checks passed. Fresh 10 km calculation: 13.1 s on a 1542×1542
grid with 47,970 covered pixels (−110 … −53 dBm). KMZ round trip
recovered the footprint exactly (47,970 pixels); GeoTIFF round trip was
bit-accurate on all covered pixels. Cached repeat completed in 3.2 s.

### Finding fixed during the test

The first run failed its cache check because `from_cache` was stored in
`coverage_storage` but never serialized by `GET /api/coverage/{id}` or
`/status`. The field is now included in both responses.

### Gotcha for future runs

If uvicorn logs `address already in use`, a stale instance is still
listening — the smoke test will silently exercise the OLD code. Kill the
listener first: `lsof -ti :8011 | xargs kill`.
