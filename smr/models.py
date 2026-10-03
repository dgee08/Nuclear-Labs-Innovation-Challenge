"""Plain data containers: what you design (RodDesign) and how you run it (Operating)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from .constants import REF, REF_GAP_M

BWRX300_THERMAL_MW = 870.0  # approximate thermal power of the BWRX-300


@dataclass(frozen=True)
class RodDesign:
    """One fuel-rod design. Defaults reproduce the ORNL 17x17 reference rod."""

    length_m: float = REF["L_m"]
    outer_diameter_m: float = REF["clad_od_m"]
    pellet_diameter_m: float = REF["pellet_d_m"]
    clad_thickness_m: float = REF["clad_thickness_m"]
    num_rods: int = REF["N_rods"]
    pellet_material: str = "UO2"  # fuel: UO2 | MOX | TRISO
    cladding_material: str = "Zircaloy"
    guide_tube_material: str = "Zircaloy"
    spacer_material: str = "SS316"
    nozzle_material: str = "SS316"
    smr_type: str = "Light Water Reactor"

    @property
    def clad_inner_diameter_m(self) -> float:
        return self.outer_diameter_m - 2.0 * self.clad_thickness_m

    @property
    def radial_gap_m(self) -> float:
        """Radial pellet-to-cladding gap (can be negative for impossible designs)."""
        return (self.clad_inner_diameter_m - self.pellet_diameter_m) / 2.0

    def with_geometry(self, outer_diameter_m: Optional[float] = None,
                      clad_thickness_m: Optional[float] = None,
                      gap_m: float = REF_GAP_M) -> "RodDesign":
        """Change OD and/or cladding thickness and re-derive the pellet size.

        The pellet always shrinks/grows so the radial gap stays at `gap_m`,
        which is how the original app treated the rod-diameter input.
        """
        od = self.outer_diameter_m if outer_diameter_m is None else outer_diameter_m
        t = self.clad_thickness_m if clad_thickness_m is None else clad_thickness_m
        return replace(self, outer_diameter_m=od, clad_thickness_m=t,
                       pellet_diameter_m=od - 2.0 * (t + gap_m))


@dataclass(frozen=True)
class Operating:
    """Operating assumptions and cost-scenario choices."""

    scenario: str = "mean"  # cost scenario: low | mean | high
    power_mode: str = "fixed_core_power"  # or "scale_with_N"
    core_power_MWt: Optional[float] = BWRX300_THERMAL_MW  # used only in fixed mode
    capacity_factor: float = 0.9
    burnup_GWd_tHM: Optional[float] = None  # None -> reactor-type default
    include_backend: bool = True
    hardware_share_in_toll: float = 0.30
    fixed_ops_per_year_usd: float = 0.0
