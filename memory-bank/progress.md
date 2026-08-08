# Progress

## Status: dev/0.20.0 complete through the review-fix pass (2026-08-07)

## What works

- Single-site coverage end-to-end with SPLAT! binary, directional
  antennas, caching, heat-map rendering, KMZ/GeoTIFF export
- Test suite: 4/4 passing (`pytest test_app.py` in mesh_map3 env)
- Vectorized post-processing verified pixel-exact against the original
  per-pixel loops

## dev/0.20.0 commits (newest last)

1. `336fe85` Bump app version to 0.20.0
2. `105f83e` Repo hygiene: removed `*.md` from .gitignore and restored
   full README.md (folding in README.txt, now deleted); ignored
   splat_cache/, output/, *.log, .DS_Store; untracked app.log + 12 SDF
   tiles (~84 MB)
3. `404edc2` Five bug fixes:
   - deep-copy per-request config (was mutating global DEFAULT_RF_CONFIG
     across concurrent requests)
   - DELETE /api/cache/clear registered before /api/cache/{site_key}
     (was always 404)
   - MultiSiteRequest.sites now List[Site] model (Dict[str,float] made
     every multi-site request 422 on the string name field)
   - calculations + cache I/O via asyncio.to_thread (event loop was
     frozen during SPLAT! runs, stalling /status polling)
   - fixed swapped (row, col) unpack of rasterio rowcol() in
     DEMHandler.latlon_to_pixel
4. `8c4e82e` Hardening: allow_credentials=False (invalid with wildcard
   origin), secrets.compare_digest for admin key, MAX_COVERAGE_RESULTS=25
   eviction; multi-site results now marked 'complete' so exports work
5. `acbee6d` Cleanup: vectorized PPM color mapping (chunked), haversine
   radius mask, KMZ PNG builder; deleted src/longley_rice.py,
   _create_fallback_dem, _extract_hgt_from_geotiff, addSignalStrengthLegend,
   aiofiles import; pruned requirements.txt; fixed 2 stale tests

## What's left / known issues

- Branch not pushed; no PR yet
- KMZ/GeoTIFF IMPORT feature exists only in the OneDrive copy — port it
  (see activeContext.md item 3)
- Multi-site path: pure-Python engine only, no antenna patterns, no
  progress, no caching, synchronous per-site loop
- Pickle used for cache blobs (unsafe if DB tampered)
- GET /api/coverage/{id} ships full arrays as JSON (multi-MB payloads);
  consider PNG/binary transport later
- numpy<2/pandas<2 pins untested against 2.x
- `elev_m` field naming: it is antenna height AGL (UI labels it
  correctly; the Pydantic description says "Elevation")
