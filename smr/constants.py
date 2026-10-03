"""All hard-coded data lives here so assumptions are easy to find and change."""
from __future__ import annotations

import math
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Reference assembly (ORNL 17x17), used for calibration and hardware allocation
# ---------------------------------------------------------------------------
REF = {
    "N_rods": 264,
    "kgU_per_assembly": 459.52,
    "kgU_per_rod": 459.52 / 264.0,  # 1.7406 kgU/rod
    "L_m": 3.6576,
    "pellet_d_m": 0.0081915,
    "clad_od_m": 0.0094996,
    "clad_thickness_m": 0.0005715,
    "guide_tubes_mass_per_assembly_kg": 9.526,
    "spacers_mass_per_assembly_kg": 6.0,
    "nozzles_mass_per_assembly_kg": 12.0,  # top + bottom combined
}

# Radial pellet-to-cladding gap implied by the reference geometry (metres).
REF_GAP_M = (REF["clad_od_m"] - 2 * REF["clad_thickness_m"] - REF["pellet_d_m"]) / 2.0

# ---------------------------------------------------------------------------
# INL WIT-style cost modules.  Units: $/kgU (front end, fab), $/kgHM (back end)
# A value of None means "only a mean is available"; the model then falls back
# to the mean for the low/high scenarios.
# ---------------------------------------------------------------------------
SCENARIOS = ["low", "mean", "high"]

WIT_UO2: Dict[str, Dict[str, Optional[float]]] = {
    "mining_milling": {"low": 41.5, "mean": 168.5, "high": 360.0},
    "conversion": {"low": 7.0, "mean": 13.8, "high": 20.8},
    "enrichment": {"low": 119, "mean": 153, "high": 188},
    "fabrication": {"low": 281, "mean": 491, "high": 702},
    "interim_store": {"low": None, "mean": 186, "high": None},
    "transport_repo": {"low": None, "mean": 32, "high": None},
    "geologic_disp": {"low": None, "mean": 709, "high": None},
}

WIT_MOX: Dict[str, Dict[str, Optional[float]]] = {
    "fabrication": {"low": 822, "mean": 1178, "high": 1660},
    # Calibrated below so MOX lifecycle matches the paper's per-rod anchor.
    "reprocessing_proxy": {"low": None, "mean": None, "high": None},
}

WIT_TRISO: Dict[str, Dict[str, Optional[float]]] = {
    "haleu_product": {"low": 8200, "mean": 15500, "high": 25500},
    "triso_fab": {"low": 1000, "mean": 4667, "high": 9000},
}

# Back-end costs are shared by all fuels (assumption inherited from the
# original tool; a good candidate for a more detailed model).
BACKEND_KEYS = ("interim_store", "transport_repo", "geologic_disp")

# ---------------------------------------------------------------------------
# Hardware proxies
# ---------------------------------------------------------------------------
HARDWARE_COST_PER_KG = {
    "Zircaloy": 420.0,
    "SS316": 310.0,
    "Inconel": 430.0,
    "Hastelloy": 430.0,
    "Graphite": 80.0,
}

MATERIAL_DENSITY = {  # kg/m^3
    "Zircaloy": 6550.0,
    "SS316": 8000.0,
    "Inconel": 8470.0,
    "Hastelloy": 8900.0,
    "Graphite": 1800.0,
}

# ---------------------------------------------------------------------------
# Reactor-type defaults
# ---------------------------------------------------------------------------
SMR_DEFAULTS = {
    "Light Water Reactor": {"qprime_kW_per_m": 18.0, "burnup_GWd_tHM": 45.0, "risk": 1.0, "ops_mult": 1.0, "maint_mult": 1.0},
    "Sodium Cooled SMRs": {"qprime_kW_per_m": 20.0, "burnup_GWd_tHM": 55.0, "risk": 1.2, "ops_mult": 1.1, "maint_mult": 1.15},
    "High-Temperature Gas-Cooled SMRs": {"qprime_kW_per_m": 10.0, "burnup_GWd_tHM": 80.0, "risk": 1.1, "ops_mult": 1.05, "maint_mult": 1.05},
    "Molten-Salt SMRs": {"qprime_kW_per_m": 15.0, "burnup_GWd_tHM": 60.0, "risk": 1.25, "ops_mult": 1.15, "maint_mult": 1.2},
}

# Choice lists used by the UI and by sweeps.
FUELS = ["UO2", "MOX", "TRISO"]
SMR_TYPES = list(SMR_DEFAULTS)
CLADDING_MATERIALS = ["Zircaloy", "SS316", "Inconel", "Hastelloy"]
GUIDE_MATERIALS = ["Zircaloy", "SS316", "Inconel"]
SPACER_MATERIALS = ["SS316", "Inconel", "Graphite"]
NOZZLE_MATERIALS = ["SS316", "Inconel", "Hastelloy"]

THERMAL_TO_ELECTRIC_EFF = 0.33
HOURS_PER_YEAR = 8760.0

# Effective uranium densities, calibrated against the reference pellet volume.
_REF_PELLET_VOL = math.pi * (REF["pellet_d_m"] / 2.0) ** 2 * REF["L_m"]
RHO_U_EFF = REF["kgU_per_rod"] / _REF_PELLET_VOL  # kgU / m^3
TRISO_REF_KGU_PER_ROD = 0.0964  # paper value (packing fraction ~0.3 proxy)
RHO_TRISO_U_EFF = TRISO_REF_KGU_PER_ROD / _REF_PELLET_VOL

# Paper anchor used to calibrate the MOX reprocessing proxy ($ per rod).
MOX_LIFECYCLE_ANCHOR_USD_PER_ROD = 5927.0


def _calibrate_mox_reprocessing_mean() -> float:
    m = REF["kgU_per_rod"]
    backend = sum(WIT_UO2[k]["mean"] for k in BACKEND_KEYS) * m
    fab = WIT_MOX["fabrication"]["mean"] * m
    needed = (MOX_LIFECYCLE_ANCHOR_USD_PER_ROD - backend - fab) / m
    return max(0.0, needed)


if WIT_MOX["reprocessing_proxy"]["mean"] is None:
    _mean = _calibrate_mox_reprocessing_mean()
    WIT_MOX["reprocessing_proxy"] = {"low": _mean * 0.7, "mean": _mean, "high": _mean * 1.3}
