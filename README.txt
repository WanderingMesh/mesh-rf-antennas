## Install gdal
conda install -c conda-forge gdal

-> 'brew install gdal' should work for Homebrew-capable systems as well.

## First-time setup: build SPLAT! (REQUIRED on every new machine/clone)
The SPLAT! source is tracked in git, but the compiled binaries are NOT
(they are architecture-specific). After cloning, run:

    ./build_splat.sh

Requires a C/C++ compiler (Xcode Command Line Tools on macOS, or
build-essential + libbz2-dev on Linux).

If the binaries are missing, the app still runs but silently falls back
to a lower-fidelity pure-Python propagation model. You'll see
"Using Python implementation (SPLAT! binary not available)" in the logs
instead of "SPLAT! service initialized - using real SPLAT! binary".
