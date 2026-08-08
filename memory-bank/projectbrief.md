# Project Brief — mesh-rf-antennas (SPLAT! RF Coverage Mapper)

## What this is

A web application for RF coverage mapping powered by the SPLAT! 1.4.2
propagation engine (ITWOM / Longley-Rice irregular terrain model) with real
SRTM terrain data. Users place a transmitter on a Leaflet map, set RF
parameters (frequency, power, antenna type/azimuth/tilt, receiver
sensitivity, climate/ground), and get a physically accurate signal-strength
heat map rendered on the map.

## Core requirements

- Terrain-aware RF propagation via the compiled SPLAT! binary (not an
  approximation) — the `-L` ITM mode, never `-c` (line-of-sight only)
- Directional antenna support: omni + 3/5/11-element Yagi patterns with
  azimuth, mechanical tilt, and tilt direction
- Single-site and multi-site (CSV upload) coverage calculation
- Persistent SQLite caching keyed on all RF parameters
- KMZ (Google Earth) and GeoTIFF (GIS) export
- Background calculation with real-time progress polling

## Repository

- GitHub: WanderingMesh/mesh-rf-antennas (private)
- Local working copy: /Users/edm/Python/mesh-rf-antennas
- Development branch: `dev/0.20.0` (all v0.20.0 work); `main` is stable
- An older, diverged copy lives in OneDrive at
  python_projects/mesh_mapper3_directional — it contains a KMZ/GeoTIFF
  IMPORT feature not yet ported to this repo (see activeContext.md)

## Owner intent

Used for planning mesh-network / LoRa / amateur radio deployments in the
Nevada (Reno) region. Physical accuracy matters more than speed, but the
UI must stay responsive during calculations.
