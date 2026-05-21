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


def _signal_to_color(dbm: float) -> tuple:
    """Map a signal strength value to an RGB color using the SPLAT! color scale."""
    for threshold, color in SIGNAL_COLORS:
        if dbm >= threshold:
            return color
    return SIGNAL_COLORS[-1][1]


def _build_coverage_png(coverage_mask, signal_strength) -> bytes:
    """
    Render coverage data as a transparent PNG for embedding in KMZ.
    Non-coverage areas are fully transparent; coverage areas are colored
    by signal strength using the SPLAT! color scale.
    """
    height = len(coverage_mask)
    width = len(coverage_mask[0])

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    pixels = img.load()

    for row in range(height):
        for col in range(width):
            if coverage_mask[row][col]:
                dbm = signal_strength[row][col]
                r, g, b = _signal_to_color(dbm)
                pixels[col, row] = (r, g, b, 180)

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
    coverage_mask = coverage_data['coverage_mask']
    signal_strength = coverage_data['signal_strength']

    # Convert numpy arrays to lists if needed
    if isinstance(coverage_mask, np.ndarray):
        coverage_mask = coverage_mask.tolist()
    if isinstance(signal_strength, np.ndarray):
        signal_strength = signal_strength.tolist()

    png_filename = 'coverage.png'
    png_bytes = _build_coverage_png(coverage_mask, signal_strength)
    kml_xml = _build_kml_xml(site_name, coverage_data, png_filename)

    # Package into KMZ (a zip containing doc.kml and the PNG)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', kml_xml)
        zf.writestr(png_filename, png_bytes)
    return buf.getvalue()


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
