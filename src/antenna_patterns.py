#!/usr/bin/env python3
"""
Antenna Pattern Generator for SPLAT!

This module generates azimuth (.az) and elevation (.el) pattern files
for common antenna types used in fixed installations.

Pattern files follow SPLAT! format with normalized field strength values (0.0 to 1.0).
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Dict

# Antenna type definitions
# Format: {type_name: {gain_dbi, h_beamwidth, v_beamwidth, front_to_back_db}}
ANTENNA_TYPES = {
    'omnidirectional': {
        'gain_dbi': 0.0,  # Typical gain for preset auto-fill
        'h_beamwidth': 360,  # Full circle
        'v_beamwidth': 90,
        'front_to_back_db': 0,  # No directionality
        'description': 'Omnidirectional (Typical: 0 dBi)'
    },
    'yagi_3el': {
        'gain_dbi': 7.0,  # Typical gain for preset auto-fill
        'h_beamwidth': 60,  # Horizontal beamwidth in degrees
        'v_beamwidth': 50,  # Vertical beamwidth in degrees
        'front_to_back_db': 20,  # Front-to-back ratio
        'description': '3-Element Yagi (Typical: 7 dBi, 60° BW)'
    },
    'yagi_5el': {
        'gain_dbi': 10.0,  # Typical gain for preset auto-fill
        'h_beamwidth': 40,
        'v_beamwidth': 40,
        'front_to_back_db': 25,
        'description': '5-Element Yagi (Typical: 10 dBi, 40° BW)'
    },
    'yagi_11el': {
        'gain_dbi': 13.0,  # Typical gain for preset auto-fill
        'h_beamwidth': 30,
        'v_beamwidth': 30,
        'front_to_back_db': 25,
        'description': '11-Element Yagi (Typical: 13 dBi, 30° BW)'
    }
}


def generate_azimuth_pattern(antenna_type: str, rotation_deg: float = 0.0) -> str:
    """
    Generate SPLAT! azimuth pattern file content.
    
    Args:
        antenna_type: Type of antenna (omnidirectional, yagi_3el, yagi_5el, yagi_11el)
        rotation_deg: Azimuth rotation in degrees (0=North, 90=East, etc.)
    
    Returns:
        String content for .az file
    """
    if antenna_type not in ANTENNA_TYPES:
        antenna_type = 'omnidirectional'
    
    params = ANTENNA_TYPES[antenna_type]
    h_beamwidth = params['h_beamwidth']
    f2b_db = params['front_to_back_db']
    
    # SPLAT!'s Azimuth() function returns standard compass bearings:
    # 0=North, 90=East (clockwise).  The first line of the .az file
    # tells SPLAT! how many degrees clockwise to rotate the raw pattern.
    # We write an unrotated pattern (boresight at index 0) and let
    # SPLAT!'s LoadPAT apply the rotation, which places the boresight
    # at the requested compass bearing.
    lines = [f"{rotation_deg:.1f}"]

    # Generate the unrotated pattern (boresight at 0°)
    for angle in range(361):
        if antenna_type == 'omnidirectional':
            pattern_value = 1.0
        else:
            # angle 0 = boresight, angle 180 = back of antenna
            relative_angle = angle if angle <= 180 else 360 - angle
            
            main_lobe_extent = h_beamwidth * 2
            main_lobe_factor = np.cos(min(relative_angle / main_lobe_extent, 1.0) * np.pi / 2) ** 2
            
            side_lobe_level = 10 ** (-20 / 20)   # -20 dB (0.1 voltage ratio)
            back_lobe_level = 10 ** (-f2b_db / 20)  # ~0.056 for 25 dB F/B
            
            if relative_angle < main_lobe_extent:
                pattern_value = max(main_lobe_factor, side_lobe_level)
            elif relative_angle < 150:
                pattern_value = side_lobe_level
            else:
                pattern_value = back_lobe_level
        
        lines.append(f"{angle}\t{pattern_value:.7f}")
    
    return "\n".join(lines)


def generate_elevation_pattern(antenna_type: str, mechanical_tilt_deg: float = 0.0,
                               tilt_azimuth_deg: float = 0.0) -> str:
    """
    Generate SPLAT! elevation pattern file content.
    
    Args:
        antenna_type: Type of antenna
        mechanical_tilt_deg: Mechanical tilt in degrees (positive=down, negative=up)
        tilt_azimuth_deg: Compass direction of the tilt in degrees (0=North, 90=East)
    
    Returns:
        String content for .el file
    """
    if antenna_type not in ANTENNA_TYPES:
        antenna_type = 'omnidirectional'
    
    params = ANTENNA_TYPES[antenna_type]
    v_beamwidth = params['v_beamwidth']
    
    # First line: mechanical tilt angle and the azimuth direction of that tilt
    lines = [f"{mechanical_tilt_deg:.1f} {tilt_azimuth_deg:.1f}"]
    
    # Generate pattern for -10 to +90 degrees elevation
    # Negative = above horizon, Positive = below horizon (SPLAT! convention)
    for elev_angle in range(-10, 91):
        if antenna_type == 'omnidirectional':
            # Omnidirectional has some vertical directionality
            # Strongest at horizon (0°), weaker at high/low angles
            if abs(elev_angle) <= 45:
                pattern_value = np.cos(elev_angle * np.pi / 180) ** 0.5
            else:
                pattern_value = 0.3
        else:
            # Directional antenna - concentrated in vertical plane
            # Main lobe centered at 0° (horizon)
            if abs(elev_angle) <= v_beamwidth / 2:
                # Main lobe
                normalized_angle = (abs(elev_angle) * 2) / v_beamwidth
                pattern_value = np.cos(normalized_angle * np.pi / 2) ** 2
            else:
                # Outside main lobe - rapid falloff
                # Typical Yagi has very little radiation at high/low angles
                falloff_db = -20
                pattern_value = 10 ** (falloff_db / 20)
        
        lines.append(f"{elev_angle}\t{pattern_value:.7f}")
    
    return "\n".join(lines)


def create_pattern_files(
    antenna_type: str,
    azimuth_deg: float,
    output_dir: Path,
    site_name: str = "tx",
    mechanical_tilt_deg: float = 0.0,
    tilt_azimuth_deg: float = 0.0
) -> Tuple[Path, Path]:
    """
    Create both .az and .el pattern files for SPLAT!
    
    Args:
        antenna_type: Type of antenna
        azimuth_deg: Antenna pointing direction (0=North, 90=East)
        output_dir: Directory to write files
        site_name: Base name for files (default: "tx")
        mechanical_tilt_deg: Beam tilt in degrees (positive=down, negative=up)
        tilt_azimuth_deg: Compass direction of the tilt (0=North, 90=East)
    
    Returns:
        Tuple of (az_file_path, el_file_path)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate pattern file contents
    az_content = generate_azimuth_pattern(antenna_type, azimuth_deg)
    el_content = generate_elevation_pattern(antenna_type, mechanical_tilt_deg=mechanical_tilt_deg,
                                            tilt_azimuth_deg=tilt_azimuth_deg)
    
    # Write files
    az_path = output_dir / f"{site_name}.az"
    el_path = output_dir / f"{site_name}.el"
    
    az_path.write_text(az_content)
    el_path.write_text(el_content)
    
    print(f"Created antenna pattern files:")
    print(f"  Azimuth: {az_path}")
    print(f"  Elevation: {el_path}")
    print(f"  Type: {ANTENNA_TYPES[antenna_type]['description']}")
    print(f"  Pointing: {azimuth_deg}° (0=North, 90=East)")
    if mechanical_tilt_deg != 0:
        print(f"  Tilt: {mechanical_tilt_deg}° toward {tilt_azimuth_deg}°")
    
    return az_path, el_path


def get_antenna_info(antenna_type: str) -> Dict:
    """
    Get information about an antenna type.
    
    Args:
        antenna_type: Type of antenna
    
    Returns:
        Dictionary with antenna parameters
    """
    if antenna_type not in ANTENNA_TYPES:
        antenna_type = 'omnidirectional'
    
    return ANTENNA_TYPES[antenna_type].copy()


def list_antenna_types() -> Dict[str, str]:
    """
    Get list of available antenna types with descriptions.
    
    Returns:
        Dictionary mapping type names to descriptions
    """
    return {name: info['description'] for name, info in ANTENNA_TYPES.items()}


if __name__ == "__main__":
    # Test pattern generation
    import tempfile
    
    print("Testing antenna pattern generation...")
    print("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for antenna_type in ANTENNA_TYPES.keys():
            print(f"\nGenerating patterns for: {antenna_type}")
            az_path, el_path = create_pattern_files(
                antenna_type=antenna_type,
                azimuth_deg=45.0,  # Northeast
                output_dir=tmpdir,
                site_name=f"test_{antenna_type}"
            )
            
            # Show first few lines
            print(f"\nFirst 5 lines of {az_path.name}:")
            lines = az_path.read_text().split('\n')[:5]
            for line in lines:
                print(f"  {line}")
    
    print("\n" + "=" * 80)
    print("Pattern generation test complete!")


