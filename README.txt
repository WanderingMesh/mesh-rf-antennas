========================================================================
mesh-rf-antennas — Setup / Installation
========================================================================

This app has ONE dependency that pip cannot install for you: the GDAL
command-line tools. Everything else comes from requirements.txt.


------------------------------------------------------------------------
Why GDAL must be installed separately (system prerequisite)
------------------------------------------------------------------------
The `elevation` package (used to fetch/clip SRTM terrain data) does not
do the raster work itself. It writes a Makefile and shells out to the
GDAL command-line programs:

    gdal_translate   gdalbuildvrt

These are native binaries, not a Python package, so they cannot be
listed in requirements.txt. If they are missing you will see:

    make: gdal_translate: No such file or directory
    Error: Failed to download terrain data: ... returned non-zero exit status 2

Note: rasterio/geopandas bundle their own private copy of the GDAL
*library* for reading rasters in Python, but that does NOT put the
gdal_translate / gdalbuildvrt *executables* on your PATH. The CLI tools
are a distinct, separate install.


------------------------------------------------------------------------
Step 1 — Install the GDAL CLI for your platform
------------------------------------------------------------------------
macOS (Homebrew):
    brew install gdal

Debian / Ubuntu:
    sudo apt-get update && sudo apt-get install -y gdal-bin

RHEL / Fedora / Rocky / Alma:
    sudo dnf install -y gdal          # older systems: sudo yum install -y gdal

Any OS via conda (macOS + Linux + Windows):
    conda install -c conda-forge gdal
    # If you use conda for GDAL, prefer installing the WHOLE scientific
    # stack from conda-forge too (numpy, pandas, rasterio, ...). Mixing a
    # conda GDAL into an otherwise pip-built env can pull in a different
    # numpy and cause an ABI mismatch ("numpy.dtype size changed").

Verify the CLI is on PATH before continuing:
    gdal_translate --version
    gdalbuildvrt --version


------------------------------------------------------------------------
Step 2 — Install the Python dependencies
------------------------------------------------------------------------
    python -m pip install -r requirements.txt

Requires numpy >= 2.0 and pandas >= 2.2.2 (they share a C ABI; older
pandas is not binary-compatible with numpy 2.x).


------------------------------------------------------------------------
Step 3 — Run
------------------------------------------------------------------------
    python app.py --host 0.0.0.0 --port 8001

The app auto-prepends the running interpreter's bin/ directory to PATH
before invoking `elevation`, so a GDAL installed inside the active
env/venv is found even when the app is not launched from an activated
shell. A system-wide GDAL (brew/apt/dnf) is already on PATH and works
without that.
