# Tech Context

## Stack

- Backend: Python 3.12, FastAPI, uvicorn (port 8001 via `python app.py`,
  8000 in Docker)
- Propagation: SPLAT! 1.4.2 compiled C++ binary (source tracked in
  `splat_src/`, binaries built per-machine with `./build_splat.sh`)
- Terrain: SRTM3 (90 m) via the `elevation` library (requires GDAL:
  `conda install -c conda-forge gdal` or `brew install gdal`)
- Frontend: Leaflet 1.9.4 + vanilla JS + Canvas, no build step
- Data: SQLite (coverage cache), pickle-serialized coverage blobs
- Export: rasterio (GeoTIFF), Pillow (KMZ PNG)
- Deployment: Docker/Compose + nginx (see docker/, deploy.sh)

## Development environment

- Conda env: `mesh_map3` (/opt/homebrew/anaconda3/envs/mesh_map3) — this
  has all dependencies. System python3 (Homebrew) does NOT.
- Run tests: `/opt/homebrew/anaconda3/envs/mesh_map3/bin/python -m pytest test_app.py -q`
  (4 tests, all passing as of dev/0.20.0)
- `test_antenna_pattern.py`, `diagnose.py`, `diagnose_splat.py`,
  `check_pattern.py`, `performance_test.py` are MANUAL diagnostic scripts,
  not pytest suites — test_antenna_pattern.py runs a full SPLAT!
  calculation if collected by pytest, so exclude it.
- GitHub auth: `gh` CLI is logged in (accounts: WanderingMesh active,
  nevada-american). Cursor's built-in GitHub session was stale at one
  point ("Bad credentials" in clone dialog) — fixable via Accounts icon
  sign-out/in; `gh` works regardless.

## Constraints

- `elevation` library shells out to `make`/gdal_translate; splat_service
  injects the interpreter's bin dir into PATH so conda-installed GDAL is
  found (see `_download_srtm_tile`).
- On failed terrain downloads, `elevation.clean()` must run or stale
  zero-byte tiles make later runs silently skip downloading
  (dem_handler.get_dem_data handles this).
- SQLite + pickle cache blobs are multi-MB; all cache I/O in async
  handlers goes through `asyncio.to_thread`.
- numpy pinned <2.0, pandas <2.0 in requirements.txt (untested against
  2.x); pydantic v1-style `.dict()` calls are used throughout.

## Version scheme

- `main` = stable; `dev/0.20.0` = current development branch; the FastAPI
  `version=` field in app.py tracks the branch version (0.20.0).
