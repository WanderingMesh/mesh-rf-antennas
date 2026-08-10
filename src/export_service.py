#!/usr/bin/env python3
"""
Export Service for Coverage Data

Generates KMZ (KML + embedded PNG) and GeoTIFF files from coverage calculation
results, enabling use in Google Earth, QGIS, ArcGIS, and other GIS tools.
"""

import io
import zipfile
import tempfile
from pathlib import Path
from typing import Dict, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image


# SPLAT! dBm color scale — maps signal strength to display colors
# Matches the color table used in splat_service.py for consistency
SIGNAL_COLORS = [
    (0,   (255,   0,   0)),
    (-10, (255, 128,   0)),
    (-20, (255, 165,   0)),
    (-30, (255, 206,   0)),
    (-40, (255, 255,   0)),
    (-50, (184, 255,   0)),
    (-60, (  0, 255,   0)),
    (-70, (  0, 208,   0)),
    (-80, (  0, 196, 196)),
    (-90, (  0, 148, 255)),
    (-100, (80,  80, 255)),
    (-110, ( 0,  38, 255)),
    (-120, (142, 63, 255)),
    (-130, (196, 54, 255)),
    (-140, (255,  0, 255)),
    (-150, (255, 194, 204)),
]


def _build_coverage_png(coverage_mask, signal_strength) -> bytes:
    """
    Render coverage data as a transparent PNG for embedding in KMZ.
    Non-coverage areas are fully transparent; coverage areas are colored
    by signal strength using the SPLAT! color scale.

    Fully vectorized: np.searchsorted maps every pixel to its color band
    at once instead of looping per pixel, which matters for the large
    rasters SPLAT! produces.
    """
    mask = np.asarray(coverage_mask, dtype=bool)
    sig = np.asarray(signal_strength, dtype=np.float64)
    height, width = mask.shape

    # SIGNAL_COLORS is ordered strongest (0 dBm) to weakest (-150 dBm).
    # Build ascending threshold arrays for searchsorted; each pixel gets
    # the color of the first (strongest) band whose threshold it meets.
    thresholds_desc = np.array([t for t, _ in SIGNAL_COLORS], dtype=np.float64)
    colors_desc = np.array([c for _, c in SIGNAL_COLORS], dtype=np.uint8)
    thresholds_asc = thresholds_desc[::-1]

    # Index of the largest threshold <= dbm; below -150 dBm clamps to the
    # weakest color.
    idx_asc = np.clip(np.searchsorted(thresholds_asc, sig, side='right') - 1, 0, len(SIGNAL_COLORS) - 1)
    idx_desc = (len(SIGNAL_COLORS) - 1) - idx_asc

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = colors_desc[idx_desc]
    rgba[..., 3] = np.where(mask, 180, 0)
    # Zero out RGB where transparent to keep the PNG clean
    rgba[~mask, :3] = 0

    img = Image.fromarray(rgba, 'RGBA')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _build_kml_xml(site_name: str, coverage_data: Dict, png_filename: str) -> str:
    """
    Build KML XML describing a ground overlay and transmitter placemark.
    """
    bounds = coverage_data.get('dem_bounds', [0, 0, 0, 0])
    west, south, east, north = bounds

    tx_lat = coverage_data.get('tx_lat', 0)
    tx_lon = coverage_data.get('tx_lon', 0)
    tx_elev = coverage_data.get('tx_elev_m', 0)
    freq = coverage_data.get('frequency_mhz', 0)
    power = coverage_data.get('tx_power_dbm', 0)
    gain = coverage_data.get('antenna_gain_dbi', 0)
    ant_type = coverage_data.get('antenna_type', 'omnidirectional')
    azimuth = coverage_data.get('antenna_azimuth', 0)
    tilt = coverage_data.get('antenna_tilt', 0)
    tilt_az = coverage_data.get('antenna_tilt_azimuth', 0)

    kml = Element('kml', xmlns='http://www.opengis.net/kml/2.2')
    doc = SubElement(kml, 'Document')
    SubElement(doc, 'name').text = f'{site_name} Coverage'

    # Coverage ground overlay
    overlay = SubElement(doc, 'GroundOverlay')
    SubElement(overlay, 'name').text = f'{site_name} Signal Coverage'
    SubElement(overlay, 'description').text = (
        f'Frequency: {freq} MHz\n'
        f'TX Power: {power} dBm\n'
        f'Antenna Gain: {gain} dBi\n'
        f'Antenna Type: {ant_type}\n'
        f'Azimuth: {azimuth}°\n'
        f'Tilt: {tilt}° toward {tilt_az}°'
    )
    icon = SubElement(overlay, 'Icon')
    SubElement(icon, 'href').text = png_filename
    box = SubElement(overlay, 'LatLonBox')
    SubElement(box, 'north').text = str(north)
    SubElement(box, 'south').text = str(south)
    SubElement(box, 'east').text = str(east)
    SubElement(box, 'west').text = str(west)

    # Transmitter placemark
    pm = SubElement(doc, 'Placemark')
    SubElement(pm, 'name').text = site_name
    SubElement(pm, 'description').text = (
        f'Lat: {tx_lat:.6f}\n'
        f'Lon: {tx_lon:.6f}\n'
        f'Antenna Height AGL: {tx_elev} m\n'
        f'Frequency: {freq} MHz\n'
        f'TX Power: {power} dBm\n'
        f'Antenna Gain: {gain} dBi\n'
        f'Antenna: {ant_type}\n'
        f'Azimuth: {azimuth}°\n'
        f'Tilt: {tilt}° toward {tilt_az}°'
    )
    point = SubElement(pm, 'Point')
    SubElement(point, 'coordinates').text = f'{tx_lon},{tx_lat},0'

    raw_xml = tostring(kml, encoding='unicode')
    # Pretty-print with XML declaration
    return parseString(raw_xml).toprettyxml(indent='  ', encoding='UTF-8').decode('utf-8')


def export_kmz(coverage_data: Dict, site_name: str = 'Coverage') -> bytes:
    """
    Export coverage data as a KMZ file (zipped KML + PNG overlay).

    Args:
        coverage_data: Dict with coverage_mask, signal_strength, dem_bounds, and metadata
        site_name: Name used for the KML document and filename

    Returns:
        KMZ file contents as bytes
    """
    # _build_coverage_png accepts ndarrays or nested lists (it normalizes
    # via np.asarray), so no list conversion is needed here.
    coverage_mask = coverage_data['coverage_mask']
    signal_strength = coverage_data['signal_strength']

    png_filename = 'coverage.png'
    png_bytes = _build_coverage_png(coverage_mask, signal_strength)
    kml_xml = _build_kml_xml(site_name, coverage_data, png_filename)

    # Package into KMZ (a zip containing doc.kml and the PNG)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', kml_xml)
        zf.writestr(png_filename, png_bytes)
    return buf.getvalue()


def import_kmz(kmz_bytes: bytes) -> Dict:
    """
    Import a previously-exported KMZ file back into coverage data.

    Extracts the PNG overlay and KML metadata, then reverse-maps
    pixel colors through SIGNAL_COLORS to recover approximate dBm
    values.  Resolution is limited to 10 dB bands because the PNG
    export uses a stepped color table.

    Args:
        kmz_bytes: Raw bytes of the KMZ file

    Returns:
        Dict matching the structure returned by SplatService.calculate_coverage,
        suitable for direct use by the frontend renderer.
    """
    import re
    from xml.etree.ElementTree import fromstring

    buf = io.BytesIO(kmz_bytes)
    with zipfile.ZipFile(buf, 'r') as zf:
        kml_text = zf.read('doc.kml').decode('utf-8')

        # Find the PNG overlay inside the archive
        png_names = [n for n in zf.namelist() if n.lower().endswith('.png')]
        if not png_names:
            raise ValueError("KMZ contains no PNG overlay")
        png_bytes = zf.read(png_names[0])

    # Parse KML — strip namespace for simpler xpath
    kml_clean = re.sub(r'\s+xmlns="[^"]+"', '', kml_text, count=1)
    root = fromstring(kml_clean)

    # Extract geographic bounds from GroundOverlay/LatLonBox
    box = root.find('.//GroundOverlay/LatLonBox')
    if box is None:
        raise ValueError("KMZ missing LatLonBox in GroundOverlay")
    north = float(box.findtext('north'))
    south = float(box.findtext('south'))
    east = float(box.findtext('east'))
    west = float(box.findtext('west'))

    # Extract TX location from Placemark/Point/coordinates
    coords_el = root.find('.//Placemark/Point/coordinates')
    tx_lon, tx_lat = 0.0, 0.0
    if coords_el is not None and coords_el.text:
        parts = coords_el.text.strip().split(',')
        tx_lon, tx_lat = float(parts[0]), float(parts[1])

    # Extract site name
    pm_name = root.findtext('.//Placemark/name') or 'Imported'

    # Parse metadata from Placemark description (written by _build_kml_xml)
    desc = root.findtext('.//Placemark/description') or ''
    def _extract(label, default=''):
        m = re.search(rf'{label}:\s*(.+)', desc)
        return m.group(1).strip() if m else default

    freq = float(_extract('Frequency', '0').replace(' MHz', ''))
    power = float(_extract('TX Power', '0').replace(' dBm', ''))
    gain = float(_extract('Antenna Gain', '0').replace(' dBi', ''))
    ant_type = _extract('Antenna', 'omnidirectional')
    azimuth = float(_extract('Azimuth', '0').replace('°', ''))
    tx_elev = float(_extract('Antenna Height AGL', '0').replace(' m', ''))

    tilt_str = _extract('Tilt', '0')
    tilt_match = re.match(r'([-\d.]+)', tilt_str)
    tilt = float(tilt_match.group(1)) if tilt_match else 0.0
    tilt_az_match = re.search(r'toward\s+([\d.]+)', tilt_str)
    tilt_az = float(tilt_az_match.group(1)) if tilt_az_match else 0.0

    # Reverse-map PNG pixels to signal strength. Vectorized nearest-color
    # matching over visible pixels only, chunked to bound the size of the
    # (N_pixels x N_colors) distance matrix — same approach as the PPM
    # parser in splat_service.py.
    img = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    pixels = np.array(img)
    height, width = pixels.shape[:2]

    ref_colors = np.array([c for _, c in SIGNAL_COLORS], dtype=np.float32)
    ref_dbm = np.array([d for d, _ in SIGNAL_COLORS], dtype=np.float64)

    coverage_mask = np.zeros((height, width), dtype=bool)
    signal_strength = np.full((height, width), -200.0)

    vis_rows, vis_cols = np.nonzero(pixels[..., 3] >= 50)
    CHUNK = 500_000
    for start in range(0, vis_rows.size, CHUNK):
        rows_c = vis_rows[start:start + CHUNK]
        cols_c = vis_cols[start:start + CHUNK]
        px = pixels[rows_c, cols_c, :3].astype(np.float32)

        dists = ((px[:, None, :] - ref_colors[None, :, :]) ** 2).sum(axis=2)
        best = np.argmin(dists, axis=1)
        dbest = dists[np.arange(best.size), best]

        # Only accept pixels close enough to a known signal color
        ok = dbest < 15000
        coverage_mask[rows_c[ok], cols_c[ok]] = True
        signal_strength[rows_c[ok], cols_c[ok]] = ref_dbm[best[ok]]

    return {
        'coverage_mask': coverage_mask.tolist(),
        'signal_strength': signal_strength.tolist(),
        'tx_lat': tx_lat,
        'tx_lon': tx_lon,
        'tx_elev_m': tx_elev,
        'frequency_mhz': freq,
        'tx_power_dbm': power,
        'antenna_gain_dbi': gain,
        'antenna_type': ant_type,
        'antenna_azimuth': azimuth,
        'antenna_tilt': tilt,
        'antenna_tilt_azimuth': tilt_az,
        'site_name': pm_name,
        'dem_bounds': [west, south, east, north],
    }


def import_geotiff(tiff_bytes: bytes) -> Dict:
    """
    Import a previously-exported GeoTIFF back into coverage data.

    This is lossless — the GeoTIFF stores raw dBm values in band 1
    and embeds site metadata as raster tags.

    Args:
        tiff_bytes: Raw bytes of the GeoTIFF file

    Returns:
        Dict matching the structure returned by SplatService.calculate_coverage.
    """
    from rasterio.io import MemoryFile

    with MemoryFile(tiff_bytes) as memfile:
        with memfile.open() as src:
            raster = src.read(1)
            nodata = src.nodata if src.nodata is not None else -9999.0
            bounds = src.bounds  # BoundingBox(left, bottom, right, top)
            tags = src.tags()

    coverage_mask = (raster != nodata).tolist()
    signal_strength = np.where(raster != nodata, raster, -200.0).astype(float).tolist()

    return {
        'coverage_mask': coverage_mask,
        'signal_strength': signal_strength,
        'tx_lat': 0.0,
        'tx_lon': 0.0,
        'tx_elev_m': 0.0,
        'frequency_mhz': float(tags.get('FREQUENCY_MHZ', 0)),
        'tx_power_dbm': float(tags.get('TX_POWER_DBM', 0)),
        'antenna_gain_dbi': float(tags.get('ANTENNA_GAIN_DBI', 0)),
        'antenna_type': tags.get('ANTENNA_TYPE', 'omnidirectional'),
        'antenna_azimuth': 0.0,
        'antenna_tilt': 0.0,
        'antenna_tilt_azimuth': 0.0,
        'site_name': tags.get('SITE_NAME', 'Imported'),
        'dem_bounds': [bounds.left, bounds.bottom, bounds.right, bounds.top],
    }


def export_geotiff(coverage_data: Dict, site_name: str = 'Coverage') -> bytes:
    """
    Export coverage data as a georeferenced GeoTIFF with signal strength in dBm.

    The raster band contains signal strength values (dBm) where coverage exists,
    and a nodata value of -9999 where there is no coverage. This preserves the
    full quantitative data for analysis in GIS tools.

    Args:
        coverage_data: Dict with coverage_mask, signal_strength, dem_bounds, and metadata
        site_name: Used for internal metadata only

    Returns:
        GeoTIFF file contents as bytes
    """
    coverage_mask = coverage_data['coverage_mask']
    signal_strength = coverage_data['signal_strength']

    if not isinstance(coverage_mask, np.ndarray):
        coverage_mask = np.array(coverage_mask, dtype=bool)
    if not isinstance(signal_strength, np.ndarray):
        signal_strength = np.array(signal_strength, dtype=np.float32)

    bounds = coverage_data.get('dem_bounds', [0, 0, 0, 0])
    west, south, east, north = bounds
    height, width = signal_strength.shape

    nodata = -9999.0
    raster = np.where(coverage_mask, signal_strength, nodata).astype(np.float32)

    transform = from_bounds(west, south, east, north, width, height)

    buf = io.BytesIO()
    with rasterio.open(
        buf,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype='float32',
        crs='EPSG:4326',
        transform=transform,
        nodata=nodata,
        compress='deflate',
    ) as dst:
        dst.write(raster, 1)
        dst.update_tags(
            SITE_NAME=site_name,
            FREQUENCY_MHZ=str(coverage_data.get('frequency_mhz', '')),
            TX_POWER_DBM=str(coverage_data.get('tx_power_dbm', '')),
            ANTENNA_GAIN_DBI=str(coverage_data.get('antenna_gain_dbi', '')),
            ANTENNA_TYPE=str(coverage_data.get('antenna_type', '')),
            BAND_UNITS='dBm',
        )

    return buf.getvalue()
