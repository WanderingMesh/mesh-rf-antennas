#!/usr/bin/env python3
"""
Configuration for Longley-Rice RF Coverage Web Application

This module contains all configuration parameters for the RF coverage
web application, including RF parameters, DEM settings, and web server
configuration.
"""

from typing import Dict, Any

# ============================================================================
# RF PARAMETERS
# ============================================================================

# Default RF parameters
DEFAULT_RF_CONFIG = {
    # Operating frequency in MHz
    'frequency_mhz': 900.0,
    
    # Transmitter power in dBm
    'tx_power_dbm': 30.0,
    
    # Receiver sensitivity in dBm
    'rx_sensitivity_dbm': -100.0,
    
    # Fade margin in dB
    'fade_margin_db': 3.0,
    
    # Antenna gain in dBi (assumed same for TX and RX)
    'antenna_gain_dbi': 0.0,
    
    # Climate zone for Longley-Rice model
    'climate_zone': 'continental_temperate'
}

# Available climate zones
CLIMATE_ZONES = {
    'continental_temperate': 'Continental Temperate',
    'maritime_temperate': 'Maritime Temperate', 
    'continental_subtropical': 'Continental Subtropical',
    'maritime_subtropical': 'Maritime Subtropical'
}

# ============================================================================
# DEM PARAMETERS
# ============================================================================

# Default DEM configuration
DEFAULT_DEM_CONFIG = {
    # DEM resolution in meters (30, 90, or 250)
    'dem_resolution': 90,
    
    # Directory to cache DEM data
    'dem_cache_dir': 'dem_cache',
    
    # Analysis radius in kilometers
    'analysis_radius_km': 20.0,
    
    # Pixel size in kilometers for coverage calculation
    'pixel_size_km': 0.1,
    
    # Fresnel zone clearance factor (0.6 = 60% clearance)
    'fresnel_clearance': 0.6,
    
    # Pre-computed viewshed database (for Nevada only)
    # Set to None to disable fast lookups and use real-time calculation
    'viewshed_db': 'nevada_viewshed.db',
    
    # SPLAT! binary directory (for realistic RF propagation)
    # If available, will use actual SPLAT! binary instead of Python implementation
    'splat_dir': 'splat_src/splat-1.4.2'
}

# ============================================================================
# COVERAGE CALCULATION PARAMETERS
# ============================================================================

# Default coverage calculation settings
DEFAULT_COVERAGE_CONFIG = {
    # Maximum number of sites for multi-site analysis
    'max_sites': 100,
    
    # Minimum coverage area to include in results (km²)
    'min_coverage_area_km2': 0.1,
    
    # Maximum coverage area for single site (km²)
    'max_single_site_area_km2': 1000.0,
    
    # Timeout for coverage calculations (seconds)
    'calculation_timeout': 300
}

# ============================================================================
# WEB SERVER CONFIGURATION
# ============================================================================

# Default web server configuration
DEFAULT_WEB_CONFIG = {
    # Server host
    'host': '0.0.0.0',
    
    # Server port
    'port': 8000,
    
    # Debug mode
    'debug': False,
    
    # CORS origins (for production, specify actual domains)
    'cors_origins': ['*'],
    
    # Maximum file upload size (MB)
    'max_upload_size_mb': 10,
    
    # Static file directory
    'static_dir': 'static',
    
    # Template directory
    'template_dir': 'templates'
}

# ============================================================================
# MAP CONFIGURATION
# ============================================================================

# Default map configuration
DEFAULT_MAP_CONFIG = {
    # Default map center (Reno, NV area)
    'default_center': {
        'lat': 39.5296,
        'lon': -119.8138,
        'zoom': 10
    },
    
    # Map tile providers
    'tile_providers': {
        'openstreetmap': {
            'url': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            'attribution': '© OpenStreetMap contributors',
            'max_zoom': 19
        },
        'satellite': {
            'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            'attribution': '© Esri',
            'max_zoom': 19
        },
        'terrain': {
            'url': 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            'attribution': '© OpenTopoMap',
            'max_zoom': 17
        }
    },
    
    # Coverage visualization colors
    'coverage_colors': {
        'min_signal': -120,  # dBm
        'max_signal': -60,   # dBm
        'colormap': 'viridis'
    }
}

# ============================================================================
# PRODUCTION CONFIGURATION
# ============================================================================

# Production-specific settings
PRODUCTION_CONFIG = {
    # Logging configuration
    'logging': {
        'level': 'INFO',
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'file': 'logs/app.log'
    },
    
    # Security settings
    'security': {
        'secret_key': 'your-secret-key-here',  # Change in production!
        'allowed_hosts': ['localhost', '127.0.0.1'],
        'https_only': False
    },
    
    # Performance settings
    'performance': {
        'max_workers': 4,
        'worker_timeout': 300,
        'cache_size_mb': 100
    }
}

# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================

def get_config(config_type: str = 'default') -> Dict[str, Any]:
    """
    Get configuration for the specified type.
    
    Args:
        config_type: Type of configuration ('default', 'production', 'development')
    
    Returns:
        Configuration dictionary
    """
    if config_type == 'production':
        return {
            'rf': DEFAULT_RF_CONFIG,
            'dem': DEFAULT_DEM_CONFIG,
            'coverage': DEFAULT_COVERAGE_CONFIG,
            'web': DEFAULT_WEB_CONFIG,
            'map': DEFAULT_MAP_CONFIG,
            'production': PRODUCTION_CONFIG
        }
    elif config_type == 'development':
        dev_config = {
            'rf': DEFAULT_RF_CONFIG.copy(),
            'dem': DEFAULT_DEM_CONFIG.copy(),
            'coverage': DEFAULT_COVERAGE_CONFIG.copy(),
            'web': DEFAULT_WEB_CONFIG.copy(),
            'map': DEFAULT_MAP_CONFIG.copy()
        }
        # Override for development
        dev_config['web']['debug'] = True
        dev_config['web']['host'] = '127.0.0.1'
        dev_config['dem']['dem_resolution'] = 250  # Faster for development
        return dev_config
    else:  # default
        return {
            'rf': DEFAULT_RF_CONFIG,
            'dem': DEFAULT_DEM_CONFIG,
            'coverage': DEFAULT_COVERAGE_CONFIG,
            'web': DEFAULT_WEB_CONFIG,
            'map': DEFAULT_MAP_CONFIG
        }

def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration parameters.
    
    Args:
        config: Configuration dictionary to validate
    
    Returns:
        True if configuration is valid
    """
    try:
        # Validate RF parameters
        rf_config = config.get('rf', {})
        assert 100 <= rf_config.get('frequency_mhz', 0) <= 6000, "Frequency must be between 100-6000 MHz"
        assert -50 <= rf_config.get('tx_power_dbm', 0) <= 50, "TX power must be between -50 and 50 dBm"
        assert -150 <= rf_config.get('rx_sensitivity_dbm', 0) <= -50, "RX sensitivity must be between -150 and -50 dBm"
        
        # Validate DEM parameters
        dem_config = config.get('dem', {})
        assert dem_config.get('dem_resolution') in [30, 90, 250], "DEM resolution must be 30, 90, or 250 meters"
        assert 1 <= dem_config.get('analysis_radius_km', 0) <= 200, "Analysis radius must be between 1-200 km"
        
        # Validate web parameters
        web_config = config.get('web', {})
        assert 1 <= web_config.get('port', 0) <= 65535, "Port must be between 1-65535"
        assert 1 <= web_config.get('max_upload_size_mb', 0) <= 100, "Max upload size must be between 1-100 MB"
        
        return True
        
    except AssertionError as e:
        print(f"Configuration validation error: {e}")
        return False
    except Exception as e:
        print(f"Configuration validation error: {e}")
        return False

# ============================================================================
# EXAMPLE CONFIGURATIONS
# ============================================================================

# Example configurations for different use cases
EXAMPLE_CONFIGS = {
    'meshtastic_900mhz': {
        'rf': {
            'frequency_mhz': 915.0,
            'tx_power_dbm': 20.0,
            'rx_sensitivity_dbm': -120.0,
            'fade_margin_db': 6.0,
            'antenna_gain_dbi': 2.0
        },
        'dem': {
            'dem_resolution': 90,
            'analysis_radius_km': 30.0
        }
    },
    
    'ham_radio_2m': {
        'rf': {
            'frequency_mhz': 146.0,
            'tx_power_dbm': 50.0,
            'rx_sensitivity_dbm': -120.0,
            'fade_margin_db': 3.0,
            'antenna_gain_dbi': 6.0
        },
        'dem': {
            'dem_resolution': 30,
            'analysis_radius_km': 100.0
        }
    },
    
    'cellular_850mhz': {
        'rf': {
            'frequency_mhz': 850.0,
            'tx_power_dbm': 40.0,
            'rx_sensitivity_dbm': -110.0,
            'fade_margin_db': 3.0,
            'antenna_gain_dbi': 10.0
        },
        'dem': {
            'dem_resolution': 90,
            'analysis_radius_km': 50.0
        }
    }
}
