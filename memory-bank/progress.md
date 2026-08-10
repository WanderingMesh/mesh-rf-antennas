# Progress

## Status: dev/0.20.0 feature-complete, smoke-tested, PR open (2026-08-10)

## What works

- Single-site coverage end-to-end with SPLAT! binary, directional
  antennas, caching, heat-map rendering, KMZ/GeoTIFF export
- KMZ/GeoTIFF IMPORT (`POST /api/coverage/import` + Import Layer UI):
  re-load previously exported layers; GeoTIFF round trip is lossless,
  KMZ round trip is 10 dB-band lossy by design
- Test suite: 4/4 passing (`pytest test_app.py` in mesh_map3 env)
- Live end-to-end smoke test: 16/16 checks passing against a real
  server + SPLAT! binary + SRTM terrain (smoke_test.py; method
  documented in memory-bank/testing.md)
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
6. `862e752` Ported KMZ/GeoTIFF import feature (endpoint, import_kmz with
   vectorized reverse color mapping, import_geotiff, frontend UI)
7. Smoke test + from_cache serialization fix (GET /api/coverage/{id} and
   /status now report whether a result came from the SQLite cache)

## What's left / known issues
- Multi-site path: pure-Python engine only, no antenna patterns, no
  progress, no caching, synchronous per-site loop
- Pickle used for cache blobs (unsafe if DB tampered)
- GET /api/coverage/{id} ships full arrays as JSON (multi-MB payloads);
  consider PNG/binary transport later
- numpy<2/pandas<2 pins untested against 2.x
- `elev_m` field naming: it is antenna height AGL (UI labels it
  correctly; the Pydantic description says "Elevation")
