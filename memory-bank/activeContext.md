# Active Context

## Current focus (as of 2026-08-10)

The KMZ/GeoTIFF import feature has been ported from the OneDrive copy,
the live end-to-end smoke test passes (16/16 checks — see
memory-bank/testing.md and smoke_test.py), and `dev/0.20.0` has been
pushed with a PR open against `main`.

## Next steps (not yet done)

0. Owner is field-testing the per-SF LoRa link budget (commit 23877d0,
   running on port 8011). Remaining accuracy roadmap if they continue:
   NLCD clutter-loss layer, field-measurement calibration mode, and
   possibly ITU-R P.1812 as the propagation engine (see the 2026-08-10
   chat assessment: ITM ignores clutter and underestimates LoRa range).
1. Review and merge the `dev/0.20.0` PR when the owner is ready.
2. Consider multi-site improvements: it still uses the pure-Python
   fallback engine (not SplatService), ignores antenna direction, and has
   no progress reporting. Also no per-site caching.
3. Consider replacing pickle with a safer serialization for cache blobs
   (pickle.loads on a tampered DB = code execution).

## Active decisions

- All 0.20.0 work stays on `dev/0.20.0`; main untouched.
- The OneDrive copy is now fully superseded (import feature ported); it
  can be retired (git history there was never pushed).
- In-memory result store capped at 25 entries (MAX_COVERAGE_RESULTS in
  app.py); evicted results survive in the SQLite cache but their
  coverage_id (export buttons) expires — acceptable for now.

## Watch out for

- The OneDrive copy's git repo had a 1.5 GB coverage_cache.db STAGED —
  do not commit/push anything from that copy without unstaging it.
- Working in OneDrive-synced folders with live SQLite files risks
  corruption/locking; this repo deliberately lives in ~/Python instead.
