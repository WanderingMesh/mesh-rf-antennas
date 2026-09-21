"""
LoRa receiver sensitivity lookup for common Meshtastic / MeshCore radio chipsets.

WHY THIS EXISTS
---------------
LoRa's chirp spread spectrum decodes signals well below the noise floor, and
how far below depends on the spreading factor (SF) and bandwidth (BW). A
fixed receiver-sensitivity number (the app's old approach) misrepresents the
link budget by up to ~27 dB across the SF7..SF12 range — enough to be wrong
about usable range by a factor of 2-4. This module resolves the actual
sensitivity from chipset + SF + BW so coverage maps reflect the radio the
user is really running.

DATA SOURCES
------------
- SX1261/62 datasheet (Semtech DS.SX1261-2.W.APP) LoRa sensitivity, 125 kHz.
  The SX1268 is the same silicon family (China-band PA variant) and shares
  the receiver specs.
- SX1276/77/78/79 datasheet (Semtech, Rev. 7), table "RF sensitivity,
  Long-Range Mode, highest LNA gain, LnaBoost, 125 kHz" (HF band). Also the
  radio in HopeRF RFM95/96/98 modules used by many first-gen boards.
- LLCC68 datasheet: pin-compatible with SX1262 with similar sensitivity but
  a -129 dBm floor and a restricted SF/BW matrix (SF7-9 @125k, SF7-10 @250k,
  SF7-11 @500k).

BANDWIDTH SCALING
-----------------
Sensitivity scales with the noise floor: halving the bandwidth halves the
noise power, improving sensitivity by ~3 dB. We store the 125 kHz column
from the datasheets and derive other bandwidths as:

    sens(bw) = sens(125 kHz) + 10 * log10(bw / 125)

Cross-checking this against the SX1276 datasheet's explicit 250 kHz column
shows agreement within 1 dB for every SF, which is inside the part-to-part
variation Semtech quotes.
"""

import math
from typing import Dict, List, Optional

# Datasheet sensitivity in dBm at 125 kHz bandwidth, keyed by spreading factor.
# SF7..SF12 only: SF5/6 are unsupported on first-gen chips and unused by
# Meshtastic/MeshCore presets, so we keep the table to values we can verify.
_SENSITIVITY_125KHZ: Dict[str, Dict[int, float]] = {
    # Second-generation Semtech silicon (Heltec V3, RAK4631, T-Echo,
    # Station G2, most current MeshCore/Meshtastic hardware)
    'sx1262': {7: -124.0, 8: -127.0, 9: -130.0, 10: -133.0, 11: -135.5, 12: -137.0},
    # Same receiver as SX1262; China-band (410-810 MHz) PA variant
    'sx1268': {7: -124.0, 8: -127.0, 9: -130.0, 10: -133.0, 11: -135.5, 12: -137.0},
    # First-generation silicon (RFM95, original T-Beam, T-LoRa v2)
    'sx1276': {7: -123.0, 8: -126.0, 9: -129.0, 10: -132.0, 11: -133.0, 12: -136.0},
    # Cost-reduced SX1262 sibling; values match SX1262 but are clamped to the
    # -129 dBm floor the LLCC68 datasheet specifies
    'llcc68': {7: -124.0, 8: -127.0, 9: -129.0, 10: -129.0, 11: -129.0, 12: -129.0},
}

# Human-readable labels for the API/UI
CHIPSET_LABELS: Dict[str, str] = {
    'sx1262': 'SX1262 (Heltec V3, RAK4631, T-Echo, most current boards)',
    'sx1268': 'SX1268 (SX1262 family, 410-810 MHz variant)',
    'sx1276': 'SX1276 / RFM95 (original T-Beam, T-LoRa, first-gen boards)',
    'llcc68': 'LLCC68 (cost-reduced SX1262; limited SF range)',
}

# Bandwidths (kHz) the supported chipsets can all be programmed to and that
# mesh firmwares actually use. LLCC68 additionally lacks 62.5 kHz.
VALID_BANDWIDTHS_KHZ: List[float] = [62.5, 125.0, 250.0, 500.0]

# LLCC68 SF support is limited per bandwidth (datasheet table 3-1)
_LLCC68_MAX_SF_BY_BW: Dict[float, int] = {125.0: 9, 250.0: 10, 500.0: 11}

# Well-known firmware presets. Frequency is included where the preset pins
# one (MeshCore's channel plan; Meshtastic LongFast's default US slot 20).
# Presets that hash the frequency from a channel name omit it so the user's
# frequency field is left untouched.
RADIO_PRESETS: List[Dict] = [
    {'id': 'meshcore_us', 'label': 'MeshCore USA/Canada (current: 62.5 kHz / SF7)',
     'frequency_mhz': 910.525, 'bandwidth_khz': 62.5, 'spreading_factor': 7},
    {'id': 'meshcore_us_legacy', 'label': 'MeshCore USA legacy (250 kHz / SF11)',
     'frequency_mhz': 910.525, 'bandwidth_khz': 250.0, 'spreading_factor': 11},
    {'id': 'meshtastic_longfast', 'label': 'Meshtastic Long Fast (US default)',
     'frequency_mhz': 906.875, 'bandwidth_khz': 250.0, 'spreading_factor': 11},
    {'id': 'meshtastic_longmod', 'label': 'Meshtastic Long Moderate',
     'frequency_mhz': None, 'bandwidth_khz': 125.0, 'spreading_factor': 11},
    {'id': 'meshtastic_longslow', 'label': 'Meshtastic Long Slow (deprecated)',
     'frequency_mhz': None, 'bandwidth_khz': 125.0, 'spreading_factor': 12},
    {'id': 'meshtastic_medslow', 'label': 'Meshtastic Medium Slow',
     'frequency_mhz': None, 'bandwidth_khz': 250.0, 'spreading_factor': 10},
    {'id': 'meshtastic_medfast', 'label': 'Meshtastic Medium Fast',
     'frequency_mhz': None, 'bandwidth_khz': 250.0, 'spreading_factor': 9},
    {'id': 'meshtastic_shortfast', 'label': 'Meshtastic Short Fast',
     'frequency_mhz': None, 'bandwidth_khz': 250.0, 'spreading_factor': 7},
    {'id': 'meshtastic_shortturbo', 'label': 'Meshtastic Short Turbo',
     'frequency_mhz': None, 'bandwidth_khz': 500.0, 'spreading_factor': 7},
]


def resolve_sensitivity(chipset: str, spreading_factor: int, bandwidth_khz: float) -> float:
    """
    Resolve receiver sensitivity (dBm) for a chipset / SF / BW combination.

    Raises ValueError with a user-facing message for unknown chipsets,
    out-of-range SFs, invalid bandwidths, or combinations the chipset
    cannot be programmed to (LLCC68 restrictions).
    """
    chipset = chipset.lower()
    if chipset not in _SENSITIVITY_125KHZ:
        raise ValueError(
            f"Unknown radio chipset '{chipset}'. "
            f"Supported: {', '.join(sorted(_SENSITIVITY_125KHZ))} (or 'manual')"
        )

    table = _SENSITIVITY_125KHZ[chipset]
    if spreading_factor not in table:
        raise ValueError(f"Spreading factor must be 7-12, got {spreading_factor}")

    if bandwidth_khz not in VALID_BANDWIDTHS_KHZ:
        raise ValueError(
            f"Bandwidth must be one of {VALID_BANDWIDTHS_KHZ} kHz, got {bandwidth_khz}"
        )

    if chipset == 'llcc68':
        max_sf = _LLCC68_MAX_SF_BY_BW.get(bandwidth_khz)
        if max_sf is None:
            raise ValueError("LLCC68 does not support 62.5 kHz bandwidth")
        if spreading_factor > max_sf:
            raise ValueError(
                f"LLCC68 supports at most SF{max_sf} at {bandwidth_khz:g} kHz "
                f"(got SF{spreading_factor})"
            )

    # Noise-floor scaling from the 125 kHz datasheet column (see module
    # docstring); rounded to 0.1 dB, which exceeds datasheet precision.
    sensitivity = table[spreading_factor] + 10.0 * math.log10(bandwidth_khz / 125.0)
    return round(sensitivity, 1)


def describe_radio_options() -> Dict:
    """
    Bundle chipset tables and firmware presets for the frontend.

    Serving this from the backend keeps a single source of truth: the UI
    computes its live sensitivity display from the same numbers the server
    uses for the actual calculation.
    """
    return {
        'chipsets': [
            {
                'id': chipset,
                'label': CHIPSET_LABELS[chipset],
                'sensitivity_125khz': _SENSITIVITY_125KHZ[chipset],
                # LLCC68 needs its restrictions surfaced so the UI can
                # disable invalid SF/BW combinations up front
                'max_sf_by_bw': _LLCC68_MAX_SF_BY_BW if chipset == 'llcc68' else None,
                'supports_62_5khz': chipset != 'llcc68',
            }
            for chipset in _SENSITIVITY_125KHZ
        ],
        'valid_bandwidths_khz': VALID_BANDWIDTHS_KHZ,
        'presets': RADIO_PRESETS,
    }
