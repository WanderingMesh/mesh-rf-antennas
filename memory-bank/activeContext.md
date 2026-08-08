# Active Context

## Current focus (as of 2026-08-07)

Development branch `dev/0.20.0` was created and a full review-driven
fix pass was completed (see progress.md for the commit-by-commit list).
The branch is LOCAL ONLY — not yet pushed to GitHub, no PR opened.

## Next steps (not yet done)

1. Manual smoke test: run the app from the `mesh_map3` conda env, do one
   single-site calculation end-to-end, confirm progress bar now updates
   smoothly while SPLAT! runs, and confirm KMZ/GeoTIFF exports open.
2. Push `dev/0.20.0` and open a PR into `main` when the owner is ready.
3. **Port the KMZ/GeoTIFF import feature** from the OneDrive copy
   (python_projects/mesh_mapper3_directional): it has
   `POST /api/coverage/import`, `import_kmz`/`import_geotiff` in
   export_service.py, plus frontend Import Layer UI in app.js/index.html.
   That copy is otherwise the same codebase; diff before porting.
4. Consider multi-site improvements: it still uses the pure-Python
   fallback engine (not SplatService), ignores antenna direction, and has
   no progress reporting. Also no per-site caching.
5. Consider replacing pickle with a safer serialization for cache blobs
   (pickle.loads on a tampered DB = code execution).

## Active decisions

- All 0.20.0 work stays on `dev/0.20.0`; main untouched.
- Keep OneDrive copy read-only as a reference until the import feature is
  ported; then it can be retired (git history there was never pushed).
- In-memory result store capped at 25 entries (MAX_COVERAGE_RESULTS in
  app.py); evicted results survive in the SQLite cache but their
  coverage_id (export buttons) expires — acceptable for now.

## Watch out for

- The OneDrive copy's git repo had a 1.5 GB coverage_cache.db STAGED —
  do not commit/push anything from that copy without unstaging it.
- Working in OneDrive-synced folders with live SQLite files risks
  corruption/locking; this repo deliberately lives in ~/Python instead.
