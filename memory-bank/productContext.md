# Product Context

## Why this exists

Planning RF deployments (LoRa/Meshtastic mesh nodes, land mobile, amateur
VHF/UHF) requires knowing where a signal actually reaches. Simple
line-of-sight tools ignore diffraction, ERP, frequency-dependent path loss,
and antenna patterns. Professional tools are expensive or command-line
only. This app wraps the free, industry-standard SPLAT! engine in a
friendly web UI.

## How it should work (user experience)

1. Click the map (or enter coordinates) to place a transmitter.
2. Set RF parameters in the left panel. Antenna type auto-fills a typical
   gain; azimuth/tilt controls appear only for directional antennas.
3. Click Calculate — a progress bar updates in real time (the server must
   never appear frozen).
4. Coverage renders as a red→purple heat map auto-scaled to the 2nd–98th
   percentile of the data so directional lobes are visible; a legend shows
   the dBm scale.
5. Layers accumulate in a panel where they can be toggled and exported
   (KMZ / GeoTIFF).

## Key product decisions

- First calculation for an area is slow (15–45 s: terrain download +
  ITWOM); identical repeat requests must return from cache in <0.1 s.
- RX sensitivity is a hard render threshold — pixels below it are
  transparent, not colored.
- LoRa spread-spectrum processing gain is intentionally NOT modeled;
  users set RX sensitivity to the gateway sensitivity at their spreading
  factor instead (documented in README "Notes on RF Modeling").
- Cache management is admin-only via Bearer token (auto-generated at
  startup and printed to console if ADMIN_API_KEY env var is unset).
