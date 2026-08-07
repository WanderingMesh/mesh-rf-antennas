# SPLAT! RF Coverage Mapper

A web application for RF coverage mapping powered by [SPLAT!](https://www.qsl.net/kd2bd/splat.html) (Signal Propagation, Loss, And Terrain analysis tool). Uses the ITWOM (Irregular Terrain With Obstructions Model) propagation engine with real SRTM terrain data to produce physically accurate coverage predictions for VHF/UHF radio systems including LoRa, land mobile radio, and amateur installations.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Directional Antennas](#directional-antennas)
- [Signal Strength Rendering](#signal-strength-rendering)
- [Exporting Coverage Data](#exporting-coverage-data)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Cache Management](#cache-management)
- [Docker Deployment](#docker-deployment)
- [Pre-Computation (Nevada)](#pre-computation-nevada)
- [Testing and Validation](#testing-and-validation)
- [Troubleshooting](#troubleshooting)
- [Notes on RF Modeling](#notes-on-rf-modeling)
- [References](#references)

---

## Features

- **SPLAT! ITWOM Backend** — Full terrain-aware RF propagation via the compiled SPLAT! 1.4.2 binary. Not a simplified approximation; this is the same engine used by professional RF engineers.
- **Directional Antenna Support** — Omnidirectional and Yagi antenna patterns (3, 5, and 11-element) with user-specified azimuth, mechanical tilt, and tilt direction. SPLAT!'s `LoadPAT` rotation is used for accurate pattern application.
- **Signal-Strength Heat Map** — Continuous color gradient from red (strongest) to purple (weakest), auto-scaled to the 2nd–98th percentile of actual signal data so directional patterns are clearly visible.
- **Interactive Leaflet Map** — Click to place a transmitter, adjust RF parameters, and see coverage rendered as a geo-referenced image overlay. Multiple simultaneous layers with toggle visibility.
- **KMZ and GeoTIFF Export** — Download any coverage layer for use in Google Earth (KMZ) or GIS software (GeoTIFF with signal strength in dBm).
- **Persistent Caching** — SQLite-backed cache keyed on all site and antenna parameters. Previously computed coverage loads instantly.
- **Multi-Site Analysis** — Upload a CSV of site locations for batch coverage calculation.
- **Real-Time Progress** — Background calculation with progress polling so the UI never freezes.

---

## Prerequisites

### SPLAT! Binary (REQUIRED on every new machine/clone)

The SPLAT! 1.4.2 **source** is tracked in git at `splat_src/splat-1.4.2/`, but the
compiled binaries are NOT — they are architecture-specific (macOS arm64 vs
Linux x86) and must be built per-machine. After cloning, run:

```bash
./build_splat.sh
```

Requires a C/C++ compiler (Xcode Command Line Tools on macOS, or
`build-essential` + `libbz2-dev` on Linux).

The compiled binary must end up at `splat_src/splat-1.4.2/splat`. Use the
standard build (not the HD variant). If the binaries are missing, the app
still runs but silently falls back to a lower-fidelity pure-Python
propagation model — you'll see `Using Python implementation (SPLAT! binary
not available)` in the logs instead of `SPLAT! service initialized`.

### GDAL

The `elevation` library used for terrain downloads requires GDAL:

```bash
conda install -c conda-forge gdal   # conda environments
brew install gdal                   # Homebrew-capable systems
```

### SRTM Terrain Data

SPLAT! uses SRTM elevation data in SDF format. Tiles are auto-downloaded and converted on first use, then cached in `splat_cache/`. The first calculation for a new geographic area takes longer while terrain data is fetched.

For faster first-run in the Nevada/Reno region, pre-cached SDF files can be placed in `splat_test/`:

```
splat_test/
├── 39:40:119:120.sdf
├── 39:40:120:121.sdf
├── 40:41:119:120.sdf
└── 40:41:120:121.sdf
```

SDF filenames use the SPLAT! convention where longitude is expressed as degrees West (positive values), not standard negative values.

### Python Environment

Python 3.10+ recommended. Install dependencies:

```bash
pip install -r requirements.txt
```

Key dependencies: FastAPI, uvicorn, numpy, Pillow, rasterio (for GeoTIFF export), pandas (for CSV upload).

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app:app --host 0.0.0.0 --port 8001

# Open in browser: http://localhost:8001
```

### First Calculation

1. Click on the map to place a transmitter (crosshair cursor), or enter coordinates manually.
2. Set RF parameters (frequency, power, antenna type/gain, receiver sensitivity, radius).
3. Click **Calculate Single Site**. Progress updates appear in real time.
4. The coverage heat map renders on the map with a signal-strength legend.

**First calculation**: 15–45 seconds (ITWOM propagation + terrain data download if needed).
**Same site again**: < 0.1 seconds (loaded from cache).

---

## Usage Guide

### Single Site Coverage

1. **Place the transmitter** — Click on the map or enter lat/lon manually.
2. **Configure RF parameters** in the left panel:

   | Parameter | Description |
   |-----------|-------------|
   | Frequency (MHz) | Carrier frequency (e.g., 900 for LoRa, 144 for 2m amateur) |
   | TX Power (dBm) | Transmitter output power |
   | Antenna Type | Omnidirectional or Yagi (3/5/11-element); gain auto-fills |
   | Antenna Gain (dBi) | Auto-filled from type but can be overridden |
   | Antenna Azimuth | Compass bearing for directional antennas (0°=N, 90°=E) |
   | Antenna Tilt | Mechanical beam tilt in degrees (positive=down) |
   | RX Sensitivity (dBm) | Receiver threshold; pixels below this are not shown |
   | Analysis Radius (km) | How far from the transmitter to compute |
   | Climate Zone | Atmospheric/ground conditions for the propagation model |

3. Click **Calculate Single Site** and watch the progress bar.
4. Results appear as a heat map overlay with statistics in the Results panel.

### Multi-Site Coverage

1. Prepare a CSV with columns: `name`, `lat`, `lon`, `elev` (elevation in meters AGL).
2. Upload via the Multi-Site panel.
3. Each site is computed independently and cached.

```csv
name,lat,lon,elev
Reno_Peak,39.5296,-119.8138,20
Carson_City,39.1638,-119.7674,15
Virginia_City,39.3096,-119.6496,10
```

### Coverage Layers

Each calculation creates a named layer in the **Coverage Layers** panel. Layers can be:
- Toggled on/off via checkbox
- Exported as **KMZ** (Google Earth) or **TIF** (GeoTIFF)
- Cleared individually or all at once

---

## Directional Antennas

### Available Antenna Types

| Antenna | Typical Gain | H Beamwidth | Front-to-Back | Use Case |
|---------|-------------|-------------|---------------|----------|
| Omnidirectional | 0 dBi | 360° | 0 dB | Base stations, repeaters, 360° coverage |
| 3-Element Yagi | 7 dBi | 60° | 20 dB | Short-medium point-to-point links |
| 5-Element Yagi | 10 dBi | 40° | 25 dB | Most popular for fixed VHF/UHF links |
| 11-Element Yagi | 13 dBi | 30° | 25 dB | Long-range, narrow beam, precise aiming |

Gain values are defaults that auto-fill in the UI but can be overridden. For example, selecting "Omnidirectional" and typing 9 dBi models a high-gain collinear omnidirectional.

### How Directionality Works

The backend generates SPLAT! `.az` (azimuth) and `.el` (elevation) pattern files:

- The azimuth pattern uses cosine-squared tapering for the main lobe, -20 dB side lobes, and a back lobe based on the front-to-back ratio.
- The pattern is written with boresight at raw index 0°. The first line of the `.az` file specifies the rotation angle. SPLAT!'s `LoadPAT` function applies the rotation internally.
- All pattern files must share the same base name as the QTH and LRP files (e.g., `tx.qth`, `tx.lrp`, `tx.az`, `tx.el` — all lowercase).

### ERP Calculation

SPLAT! uses Effective Radiated Power:

```
ERP (watts) = 10 ^ ((TX_power_dBm + Antenna_gain_dBi - System_loss_dB - 30) / 10)
```

Example: 30 dBm TX + 13 dBi Yagi = 43 dBm EIRP ≈ 20 watts ERP.

### Azimuth Reference

- **0°** = North, **90°** = East, **180°** = South, **270°** = West
- The UI shows both degrees and compass direction (N, NE, E, etc.)
- The azimuth slider only appears when a directional antenna type is selected

---

## Signal Strength Rendering

The PPM output from SPLAT! uses 16 discrete color bands (0 to -150 dBm in 10 dB steps). With the `-sc` (smooth contours) flag, colors are continuously interpolated between bands. The backend parses these interpolated colors using inverse-distance weighting against the known reference colors to recover sub-10 dB signal resolution.

The frontend auto-scales the color gradient to the **2nd–98th percentile** of the data, clamping outliers. This ensures that the meaningful signal variation (typically 20–40 dB) fills the entire red-to-purple color range, making directional patterns and terrain effects clearly visible.

| Color | Meaning |
|-------|---------|
| Red | Strongest signal (near transmitter) |
| Orange/Yellow | Strong signal |
| Green | Medium signal |
| Cyan/Blue | Weak signal |
| Purple/Magenta | Weakest signal (near coverage edge) |
| Transparent | No coverage (below RX sensitivity) |

---

## Exporting Coverage Data

### KMZ Export (Google Earth)

Click the **KMZ** button next to any coverage layer. The download contains:
- A colored PNG ground overlay with signal strength
- KML file with geographic bounds and transmitter placemark
- Packaged as a standard KMZ (zipped KML) file

### GeoTIFF Export (GIS Software)

Click the **TIF** button next to any coverage layer. The download is a georeferenced raster with:
- Signal strength values in dBm per pixel
- Nodata value of -9999
- EPSG:4326 coordinate reference system
- Compatible with QGIS, ArcGIS, GDAL, etc.

### API Endpoints for Export

```
GET /api/coverage/{coverage_id}/export/kmz
GET /api/coverage/{coverage_id}/export/geotiff
```

---

## Architecture

### Project Structure

```
mesh_mapper3_directional/
├── app.py                      # FastAPI application, routes, caching
├── config.py                   # Configuration (env vars, defaults)
├── requirements.txt            # Python dependencies
├── src/
│   ├── splat_service.py        # SPLAT! binary wrapper, PPM/KML parsing
│   ├── antenna_patterns.py     # .az/.el pattern file generation
│   ├── coverage_calculator.py  # Coverage orchestration
│   ├── export_service.py       # KMZ and GeoTIFF export
│   ├── dem_handler.py          # SRTM DEM download and processing
│   ├── splat_longley_rice.py   # Python fallback (when SPLAT! binary unavailable)
│   └── viewshed_lookup.py      # Pre-computed viewshed DB lookup
├── templates/
│   └── index.html              # Main UI (Jinja2 + Leaflet)
├── static/
│   ├── css/style.css
│   └── js/app.js               # Frontend logic (map, coverage rendering)
├── splat_src/
│   └── splat-1.4.2/            # SPLAT! source and compiled binary
├── splat_cache/                # Cached SDF terrain tiles (auto-populated)
├── coverage_db/                # SQLite coverage cache
└── docker/                     # Docker deployment files
```

### Request Flow

```
User clicks "Calculate"
  → POST /api/coverage/single
  → Generate coverage_id, start background task, return immediately
  → Frontend polls GET /api/coverage/{id}/status every second
  → Background task:
      1. Check SQLite cache (site_key lookup)
         ├─ Cached → deserialize and return instantly
         └─ Not cached → proceed to SPLAT!
      2. Create input files (QTH, LRP, AZ, EL)
      3. Download/convert SRTM terrain to SDF if needed
      4. Run SPLAT! binary (-L -dbm -sc flags)
      5. Parse PPM output → coverage_mask + signal_strength arrays
      6. Crop to analysis radius, apply circular distance mask
      7. Save to SQLite cache
      8. Return coverage data to frontend
  → Frontend renders heat map on HTML canvas
  → Canvas overlaid on Leaflet map using KML geographic bounds
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, uvicorn, Python 3.10+ |
| Propagation | SPLAT! 1.4.2 (ITWOM), compiled C++ binary |
| Frontend | Leaflet.js, vanilla JavaScript, Canvas API |
| Map tiles | OpenStreetMap, Esri Satellite, OpenTopoMap |
| Data | SQLite (cache), SRTM SDF (terrain), numpy arrays |
| Export | rasterio (GeoTIFF), Pillow (KMZ PNG), xml.etree (KML) |
| Deployment | Docker, Docker Compose, Nginx reverse proxy |

---

## API Reference

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web interface |
| `POST` | `/api/coverage/single` | Start single-site calculation |
| `POST` | `/api/coverage/multi` | Start multi-site calculation |
| `POST` | `/api/coverage/upload` | Upload CSV of sites |
| `GET` | `/api/coverage/{id}/status` | Poll calculation progress |
| `GET` | `/api/coverage/{id}` | Retrieve coverage data |
| `GET` | `/api/coverage/{id}/export/kmz` | Download KMZ file |
| `GET` | `/api/coverage/{id}/export/geotiff` | Download GeoTIFF file |
| `GET` | `/api/coverage/{id}/map` | Coverage map image (PNG) |
| `GET` | `/api/config` | Current configuration |
| `GET` | `/api/health` | Health check |

### Admin Endpoints (Bearer token required)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/cache/list` | List cached calculations |
| `DELETE` | `/api/cache/{site_key}` | Delete specific cached site |
| `DELETE` | `/api/cache/clear` | Clear all cached data |

Interactive API docs are available at `/docs` (Swagger UI) or `/redoc` (ReDoc).

---

## Cache Management

### How Caching Works

All coverage calculations are cached in `coverage_db/coverage_cache.db`. The cache key includes all parameters that affect the result:

```
{lat}_{lon}_{elev}_{freq}_{power}_{gain}_{type}_{azimuth}
```

Changing any parameter (including antenna type or azimuth) produces a new cache key and triggers a fresh calculation. Identical requests return cached results in < 0.1 seconds.

### Admin API Key

Cache management endpoints require a Bearer token. The key is either:
- Set via environment variable: `export ADMIN_API_KEY="your-key"`
- Auto-generated at startup (printed to console — save it)

### Managing the Cache

```bash
# List cached sites
curl -H "Authorization: Bearer $ADMIN_KEY" http://localhost:8001/api/cache/list

# Delete a specific cached site
curl -X DELETE -H "Authorization: Bearer $ADMIN_KEY" \
  http://localhost:8001/api/cache/39.572360_-119.801940_1490.0_900.0_30.0

# Clear all cached data
curl -X DELETE -H "Authorization: Bearer $ADMIN_KEY" \
  http://localhost:8001/api/cache/clear
```

### Manual Cache Reset

```bash
# Delete the database file (recreated automatically on restart)
rm coverage_db/coverage_cache.db
```

---

## Docker Deployment

### Prerequisites

1. Docker Desktop installed
2. SPLAT! source at `splat_src/splat-1.4.2/` (compiled during Docker build)

### Quick Start

```bash
# Option 1: Docker Compose (recommended)
cd docker
docker-compose up --build -d

# Option 2: Helper script
cd docker
chmod +x build.sh
./build.sh

# Option 3: Direct build from project root
docker build -f docker/Dockerfile -t rf-coverage-mapper .
docker run -d --name rf-coverage -p 8000:8000 \
  -v rf_coverage_cache:/app/coverage_db \
  -v rf_dem_cache:/app/dem_cache \
  rf-coverage-mapper
```

Access at **http://localhost:8000**.

### Persistent Volumes

| Volume | Purpose |
|--------|---------|
| `coverage_cache` | Cached RF coverage calculations |
| `dem_cache` | Downloaded terrain elevation data |
| `splat_cache` | SPLAT! SDF terrain tiles |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_API_KEY` | `changeme` | API key for cache management |
| `CONFIG_TYPE` | `default` | Configuration profile |

### Container Management

```bash
docker-compose logs -f          # View logs
docker-compose down             # Stop
docker-compose down -v          # Stop and remove all cached data
docker-compose up --build       # Rebuild after code changes
```

### Build Information

- **Base Image**: Python 3.11 Slim (Debian Bookworm)
- **SPLAT! Version**: 1.4.2 (Standard, not HD)
- **Terrain Data**: SRTM3 (90m resolution)
- **Exposed Port**: 8000

---

## Pre-Computation (Nevada)

For instant results in the Nevada region, you can pre-compute terrain viewshed data using `precompute_nevada.py`.

```bash
pip install tqdm

# Default 5km grid (recommended) — takes 2-4 hours
python precompute_nevada.py

# Custom grid spacing
python precompute_nevada.py --resolution 2.5   # Higher accuracy, 8-12 hours
python precompute_nevada.py --resolution 10    # Faster, 30-60 minutes
```

| Grid Spacing | Compute Time | Database Size | Accuracy |
|-------------|-------------|---------------|----------|
| 10 km | ~1 hour | ~150 MB | Development/testing |
| 5 km | ~3 hours | ~800 MB | Production (recommended) |
| 2.5 km | ~10 hours | ~3 GB | High precision |

The resulting `nevada_viewshed.db` is used automatically when present. For production, pre-compute on a development machine and copy the database to the server.

---

## Testing and Validation

### Verifying Parameters Affect Coverage

To confirm the propagation model is working correctly (not just line-of-sight):

1. **Antenna gain**: Change from 0 to 6 dBi — coverage area should increase dramatically (~4x).
2. **Frequency**: Change from 144 to 900 MHz — coverage should shrink significantly (~16 dB more path loss).
3. **Power**: Change from 50W to 5W — coverage radius should decrease (~70% of original).
4. **Height**: Change from 20m to 50m — coverage should increase, especially in valleys.
5. **Directional vs omni**: Same site with 11-element Yagi vs omnidirectional — Yagi should show elongated coverage in the azimuth direction.

### Visual Indicators of Correct Behavior

- Coverage maps show **colored signal strength gradients** (not flat green).
- Coverage extends **beyond pure line-of-sight** due to terrain diffraction.
- Calculation takes **15–45 seconds** (not 5 seconds — that would indicate LOS-only mode).
- Mountains **block signal** but don't eliminate it completely (diffraction over ridges).
- Directional antennas show **elongated patterns** pointing in the azimuth direction.

### Climate Zone Mapping

The LRP file supports seven ITU climate zones:

| Code | Climate | Example Region |
|------|---------|----------------|
| 1 | Equatorial | Amazon, Congo |
| 2 | Continental Subtropical | Southern US, Mediterranean |
| 3 | Maritime Subtropical | Southeast Asia, Caribbean |
| 4 | Desert | Sahara, Mojave, Great Basin |
| 5 | Continental Temperate | Northern US, Central Europe |
| 6 | Maritime Temperate (Land) | UK, Pacific Northwest |
| 7 | Maritime Temperate (Sea) | Open ocean, coastal |

---

## Troubleshooting

### Coverage Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| No coverage shown | RX sensitivity too strict | Make less negative (e.g., -120 instead of -100) |
| All parameters produce identical maps | Stale cache | Clear cache: `rm coverage_db/coverage_cache.db` |
| Coverage is a perfect circle | Terrain data missing | Check `splat_cache/` for SDF files; verify internet access |
| Calculation times out | Radius too large | Reduce analysis radius (e.g., 30 km instead of 80 km) |
| Terrain shows as sea level | Wrong SPLAT! build | Use standard SPLAT!, not HD variant |

### Directional Antenna Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| Azimuth controls don't appear | Omnidirectional selected | Select a Yagi antenna type |
| Coverage looks same as omni | Stale cache | Clear cache and recalculate |
| Side lobe appears stronger than main | Black pixel artifacts (fixed) | Update to latest code; clear cache |

### Server Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| "Database locked" | Multiple processes accessing SQLite | Restart the server |
| 403 on cache endpoints | Wrong/missing admin key | Check server startup logs for the key |
| SPLAT! binary not found | Not compiled | Run `./build_splat.sh` from the project root |
| Port already in use | Another process | Check with `lsof -i :8001` |

### Checking Server Logs

Key log messages to look for:

```
Running SPLAT! command: .../splat -t tx.qth -L 2.0 -dbm -sc ...   ← Correct mode
Created antenna pattern files: tx.az, tx.el                        ← Patterns loaded
Using cached coverage for site_key ...                             ← Cache hit
```

The `-L` flag (not `-c`) is critical — `-c` only does line-of-sight and ignores all RF parameters.

---

## Notes on RF Modeling

### What SPLAT! Models

- Terrain-based path loss (ITWOM/Longley-Rice irregular terrain model)
- Knife-edge diffraction over ridgelines
- Fresnel zone obstruction
- Atmospheric refraction (4/3 earth radius)
- Ground conductivity and dielectric effects
- Antenna radiation patterns (azimuth and elevation)
- ERP (Effective Radiated Power) from TX power + antenna gain

### What SPLAT! Does Not Model

- Modulation-specific processing gain (e.g., LoRa chirp spread spectrum)
- Multipath fading statistics
- Building penetration loss
- Vegetation attenuation
- Co-channel interference
- Protocol-layer behavior (duty cycle, adaptive data rate, etc.)

### LoRaWAN Planning Notes

SPLAT! computes raw received power — it has no knowledge of LoRa's spread spectrum processing gain. For LoRaWAN coverage planning:

- Set RX Sensitivity to your gateway's sensitivity at the target spreading factor (e.g., -137 dBm for SF12/125kHz).
- Add 10–15 dB fade margin for real-world reliability.
- LoRa can decode signals well below the noise floor (7–20 dB processing gain depending on SF), so real coverage typically extends beyond what the map shows at conservative thresholds.

---

## References

- [SPLAT! — Signal Propagation, Loss, And Terrain analysis](https://www.qsl.net/kd2bd/splat.html)
- [ITWOM — Irregular Terrain With Obstructions Model](https://www.its.bldrdoc.gov/resources/radio-propagation-software/itm/itm.aspx)
- [Longley-Rice Model (NTIA)](https://www.its.bldrdoc.gov/media/47075/longley-rice.pdf)
- [SRTM — Shuttle Radar Topography Mission](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm-1)
