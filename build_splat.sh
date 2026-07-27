#!/usr/bin/env bash
#
# build_splat.sh - Compile SPLAT! 1.4.2 and srtm2sdf for this machine.
#
# WHY THIS EXISTS: Compiled binaries are architecture-specific (macOS arm64,
# Linux x86_64, etc.) so they are NOT tracked in git - only the source is.
# Run this once after cloning the repo on any new machine. The app
# (src/coverage_calculator.py) looks for the binaries at
# splat_src/splat-1.4.2/splat and splat_src/splat-1.4.2/utils/srtm2sdf;
# if they are missing it silently falls back to a lower-fidelity pure-Python
# propagation model, so make sure this script succeeds!
#
# The compile flags below intentionally mirror docker/Dockerfile so local
# and containerized builds behave identically.
#
set -euo pipefail

SPLAT_DIR="$(cd "$(dirname "$0")" && pwd)/splat_src/splat-1.4.2"

if [[ ! -f "$SPLAT_DIR/splat.cpp" ]]; then
    echo "ERROR: SPLAT! source not found at $SPLAT_DIR" >&2
    echo "Did you clone the full repository?" >&2
    exit 1
fi

echo "Building SPLAT! (standard resolution) in $SPLAT_DIR ..."
cd "$SPLAT_DIR"

# CRITICAL: use std-parms.h (1200x1200 terrain tiles), NOT hd-parms.h.
# The app's terrain pipeline (srtm2sdf) produces standard-resolution SDF
# files; an HD-built splat binary would misread them.
cp std-parms.h splat.h

# -Wno-register: splat.cpp uses the deprecated 'register' keyword, which
# modern C++ compilers warn about (and C++17 removed).
g++ -Wall -O3 -ffast-math -fomit-frame-pointer -Wno-register \
    -o splat splat.cpp itwom3.0.cpp -lm -lbz2

# srtm2sdf is old K&R-style C; gnu89 keeps legacy compilers behavior.
cd utils
gcc -Wall -O3 -std=gnu89 -o srtm2sdf srtm2sdf.c -lm -lbz2

echo
echo "Build complete:"
ls -la "$SPLAT_DIR/splat" "$SPLAT_DIR/utils/srtm2sdf"
echo
echo "Verify: the app should now log 'SPLAT! service initialized - using real SPLAT! binary'"
