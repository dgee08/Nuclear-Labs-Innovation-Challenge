"""Cost and fuel-lifetime model.

The arithmetic is unchanged from the original `estimate_costs_and_interval`;
what changed is the shape of the output: one flat dict with explicit units in
the key names, so results drop straight into a pandas DataFrame.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, Optional

from .constants import (
    BACKEND_KEYS, HARDWARE_COST_PER_KG, HOURS_PER_YEAR, MATERIAL_DENSITY, REF,
    RHO_TRISO_U_EFF, RHO_U_EFF, SMR_DEFAULTS, THERMAL_TO_ELECTRIC_EFF,
    WIT_MOX, WIT_TRISO, WIT_UO2,
)
from .models import Operating, RodDesign


# ----------------------------- small helpers -------------------------------
def _cyl_volume(diameter_m: float, length_m: float) -> float:
    return math.pi * (diameter_m / 2.0) ** 2 * length_m


def _pick(table: Dict[str, Optional[float]], scenario: str) -> float:
    """Scenario value, falling back to the mean when only a mean exists."""
    v = table.get(scenario)
    return float(table["mean"] if v is None else v)


def _density(material: str) -> float:
    return float(MATERIAL_DENSITY.get(material, 8000.0))


def _hardware_cost_per_kg(material: str) -> float:
    return float(HARDWARE_COST_PER_KG.get(material, HARDWARE_COST_PER_KG["SS316"]))


def heavy_metal_mass_per_rod_kg(fuel: str, pellet_d_m: float, length_m: float) -> float:
    volume = _cyl_volume(pellet_d_m, length_m)
    if fuel in ("UO2", "MOX"):
        return RHO_U_EFF * volume
    if fuel == "TRISO":
        return RHO_TRISO_U_EFF * volume
    raise ValueError(f"Unknown fuel: {fuel}")


def cladding_mass_per_rod_kg(outer_d_m: float, length_m: float, thickness_m: float, material: str) -> float:
    inner_d = max(0.0, outer_d_m - 2.0 * thickness_m)
    volume = max(0.0, _cyl_volume(outer_d_m, length_m) - _cyl_volume(inner_d, length_m))
    return volume * _density(material)


def _fuel_cycle_unit_costs(fuel: str, scenario: str):
    """Return ($/kg front end, $/kg total fabrication, $/kg back end)."""
    backend = sum(_pick(WIT_UO2[k], scenario) for k in BACKEND_KEYS)
    if fuel == "UO2":
        front = sum(_pick(WIT_UO2[k], scenario) for k in ("mining_milling", "conversion", "enrichment"))
        fab = _pick(WIT_UO2["fabrication"], scenario)
    elif fuel == "MOX":
        front = _pick(WIT_MOX["reprocessing_proxy"], scenario)
        fab = _pick(WIT_MOX["fabrication"], scenario)
    elif fuel == "TRISO":
        front = _pick(WIT_TRISO["haleu_product"], scenario)
        fab = _pick(WIT_TRISO["triso_fab"], scenario)
    else:
        raise ValueError(f"Unknown pellet_material: {fuel}")
    return front, fab, backend


def resolved_burnup(design: RodDesign, op: Operating) -> float:
    """Burnup actually used (GWd/tHM): the override if given, else the reactor default."""
    if op.burnup_GWd_tHM is not None:
        return float(op.burnup_GWd_tHM)
    return float(SMR_DEFAULTS[design.smr_type]["burnup_GWd_tHM"])


# ------------------------------- main model --------------------------------
def evaluate(design: RodDesign, op: Operating = Operating()) -> Dict[str, float]:
    """Evaluate one design under one set of operating assumptions.

    Returns a flat dict. `num_rods` is the rod count actually used, which in
    fixed-core-power mode is recomputed from power and linear heat rate (so the
    rod count you pass in is ignored in that mode).
    """
    smr = SMR_DEFAULTS[design.smr_type]
    qprime = smr["qprime_kW_per_m"]
    burnup = resolved_burnup(design, op)

    # Power and rod count
    if op.power_mode == "fixed_core_power":
        if op.core_power_MWt is None:
            raise ValueError("core_power_MWt must be provided in fixed_core_power mode.")
        power_kW = max(1.0, float(op.core_power_MWt) * 1000.0)
        n_rods = max(1, int(math.ceil(power_kW / (qprime * design.length_m))))
        design = replace(design, num_rods=n_rods)
    elif op.power_mode == "scale_with_N":
        power_kW = max(1.0, design.num_rods * qprime * design.length_m)
    else:
        raise ValueError(f"Unknown power_mode: {op.power_mode}")
    n = design.num_rods

    # Masses
    m_hm_rod = heavy_metal_mass_per_rod_kg(design.pellet_material, design.pellet_diameter_m, design.length_m)
    m_clad = cladding_mass_per_rod_kg(design.outer_diameter_m, design.length_m,
                                      design.clad_thickness_m, design.cladding_material)

    # Hardware cost (reference-assembly hardware split evenly over the rods)
    hw_cost_rod = (
        m_clad * _hardware_cost_per_kg(design.cladding_material)
        + REF["guide_tubes_mass_per_assembly_kg"] / max(1, n) * _hardware_cost_per_kg(design.guide_tube_material)
        + REF["spacers_mass_per_assembly_kg"] / max(1, n) * _hardware_cost_per_kg(design.spacer_material)
        + REF["nozzles_mass_per_assembly_kg"] / max(1, n) * _hardware_cost_per_kg(design.nozzle_material)
    )
    hw_cost_total = hw_cost_rod * n

    # Fuel-cycle costs (part of the fabrication toll is hardware; avoid double counting)
    c_front, c_fab_total, c_backend = _fuel_cycle_unit_costs(design.pellet_material, op.scenario)
    hw_share = max(0.0, min(0.9, float(op.hardware_share_in_toll)))
    c_fab_process = (1.0 - hw_share) * c_fab_total

    cost_front = n * m_hm_rod * c_front
    cost_fab = n * m_hm_rod * c_fab_process
    cost_backend = n * m_hm_rod * c_backend if op.include_backend else 0.0
    procurement = cost_front + cost_fab + hw_cost_total
    lifecycle = procurement + cost_backend

    # Burnup-limited lifetime
    e_th_kwh = burnup * (m_hm_rod * n / 1000.0) * 24.0 * 1_000_000.0  # GWd/t * t * 24 GWh/GWd * 1e6 kWh/GWh
    annual_kwh = power_kW * float(op.capacity_factor) * HOURS_PER_YEAR
    interval_yr = max(0.25, e_th_kwh / max(1.0, annual_kwh))

    # Annual costs (transparent proxies)
    operational = (float(op.fixed_ops_per_year_usd) + procurement / interval_yr) * smr["ops_mult"]
    maintenance = 0.03 * procurement * smr["maint_mult"]

    # Normalised metrics
    e_th_mwh_rod = (e_th_kwh / max(1, n)) / 1000.0
    proc_rod = procurement / max(1, n)
    life_rod = lifecycle / max(1, n)
    proc_mwh_th = proc_rod / max(1e-9, e_th_mwh_rod)
    life_mwh_th = life_rod / max(1e-9, e_th_mwh_rod)

    return {
        # headline
        "core_power_MWt": power_kW / 1000.0,
        "num_rods": n,
        "rod_change_interval_yr": interval_yr,
        # totals
        "procurement_total_usd": procurement,
        "lifecycle_total_usd": lifecycle,
        "operational_usd_per_year": operational,
        "maintenance_usd_per_year": maintenance,
        # cost breakdown (front + fab + hardware = procurement; + backend = lifecycle)
        "cost_front_end_usd": cost_front,
        "cost_fabrication_usd": cost_fab,
        "cost_hardware_usd": hw_cost_total,
        "cost_back_end_usd": cost_backend,
        # per rod / per energy
        "mHM_kg_per_rod": m_hm_rod,
        "E_th_MWh_per_rod": e_th_mwh_rod,
        "procurement_usd_per_rod": proc_rod,
        "lifecycle_usd_per_rod": life_rod,
        "procurement_usd_per_MWh_th": proc_mwh_th,
        "lifecycle_usd_per_MWh_th": life_mwh_th,
        "procurement_usd_per_MWh_e": proc_mwh_th / THERMAL_TO_ELECTRIC_EFF,
        "lifecycle_usd_per_MWh_e": life_mwh_th / THERMAL_TO_ELECTRIC_EFF,
        # assumptions actually used (handy for filtering and debugging)
        "qprime_kW_per_m": qprime,
        "burnup_GWd_tHM": burnup,
        "clad_mass_kg_per_rod": m_clad,
    }


# Display metadata shared by the app and the plots: key -> (label, unit)
METRICS = {
    "lifecycle_usd_per_MWh_e": ("Lifecycle cost", "$/MWh (electric)"),
    "lifecycle_usd_per_MWh_th": ("Lifecycle cost", "$/MWh (thermal)"),
    "procurement_usd_per_MWh_e": ("Procurement cost", "$/MWh (electric)"),
    "rod_change_interval_yr": ("Rod change interval", "years"),
    "procurement_total_usd": ("Core procurement cost", "$"),
    "lifecycle_total_usd": ("Core lifecycle cost", "$"),
    "operational_usd_per_year": ("Operational cost", "$/year"),
    "maintenance_usd_per_year": ("Maintenance cost", "$/year"),
    "num_rods": ("Rod count", "rods"),
    "core_power_MWt": ("Core thermal power", "MWt"),
}


def metric_label(key: str) -> str:
    label, unit = METRICS.get(key, (key, ""))
    return f"{label} ({unit})" if unit else label
