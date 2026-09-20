# System Patterns

## Architecture

```
Browser (Leaflet + vanilla JS, static/js/app.js)
  → FastAPI (app.py)
      → CoverageCalculator (src/coverage_calculator.py)
          → SplatService (src/splat_service.py)      ← preferred path
          → splat_longley_rice.py (pure Python)      ← fallback if binary missing
      → SQLite cache (coverage_db/coverage_cache.db)
      → export_service.py (KMZ / GeoTIFF)
```

## Request flow (single site)

1. `POST /api/coverage/single` stores a 'processing' entry in
   `coverage_storage` (in-memory dict, capped at 25 via
   `prune_coverage_storage()`), spawns `_calculate_coverage_background`,
   and returns the coverage_id immediately.
2. Background task: cache lookup by `site_key` (every RF parameter is in
   the key) → on miss, runs the calculation **via `asyncio.to_thread`**
   (critical: the work is synchronous; running it on the event loop
   freezes `/status` polling).
3. Frontend polls `GET /api/coverage/{id}/status` 1×/s, then fetches the
   full arrays from `GET /api/coverage/{id}` and renders on a canvas
   overlaid with `L.imageOverlay` using SPLAT!'s KML bounds.

## SPLAT! integration invariants (do not break these)

- Use `-L 2.0 -dbm -sc -m 1.333 -metric -R {radius} -db {sens} -ngs -N`.
  `-L` (not `-c`!) enables full ITM propagation; `-c` is LOS-only.
- QTH files: SPLAT! treats west longitude as POSITIVE; elevation line must
  say "meters" explicitly or SPLAT! assumes feet.
- SDF tiles are named `min_lat:max_lat:min_west:max_west.sdf` with
  longitude in degrees WEST (positive).
- Antenna pattern files (.az/.el) must share the QTH/LRP base filename
  (lowercase "tx"). The .az first line is the rotation angle; the pattern
  is written unrotated (boresight at 0°) and SPLAT!'s LoadPAT rotates it.
- ERP (watts) = 10^((tx_dBm + gain_dBi − loss_dB − 30)/10), written into
  the LRP file.
- PPM output parsing: 16 reference colors (0 to −150 dBm in 10 dB steps);
  with `-sc` colors are interpolated, so dBm is recovered by
  inverse-distance weighting the two nearest reference colors
  (vectorized, chunked at 500k pixels). Pixels farther than
  MAX_COLOR_DIST_SQ=15000 from every reference color are rejected.

## Other patterns

- Per-request config MUST be `copy.deepcopy(config)` — a shallow copy
  shares the nested 'rf'/'dem' dicts and mutates global defaults.
- FastAPI matches routes in declaration order: static routes like
  `/api/cache/clear` must be registered BEFORE `/api/cache/{site_key}`.
- Coverage arrays cross module boundaries as JSON-friendly nested lists;
  `coverage_calculator.py` converts them back to NumPy on receipt.
- rasterio's `rowcol()` returns `(row, col)` — keep the unpack order
  straight (there was a swap bug here once; test_app.py now asserts it).
- Frontend heat map: percentile (2–98%) auto-scaled continuous gradient
  (`GRADIENT_STOPS` / `lerpGradient` in app.js), NOT the fixed SPLAT!
  color table (that one is only used for KMZ export consistency).
