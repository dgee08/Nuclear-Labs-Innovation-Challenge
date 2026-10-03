"""Run many evaluations and return one tidy DataFrame (one row per case)."""
from __future__ import annotations

import itertools
import warnings
from dataclasses import fields, replace
from typing import Mapping, Optional, Sequence, Tuple

import pandas as pd

from .cost_model import evaluate, resolved_burnup
from .models import Operating, RodDesign

DESIGN_FIELDS = {f.name for f in fields(RodDesign)}
OPERATING_FIELDS = {f.name for f in fields(Operating)}


def build_case(base_design: RodDesign, base_op: Operating,
               overrides: Mapping[str, object]) -> Optional[Tuple[RodDesign, Operating]]:
    """Apply parameter overrides to a base case.

    Names may be any RodDesign or Operating field.  If outer diameter or
    cladding thickness is overridden without also overriding the pellet
    diameter, the pellet is re-derived so the radial gap stays what it is in
    the base design.  Returns None when the geometry is impossible (pellet <= 0).
    """
    unknown = set(overrides) - DESIGN_FIELDS - OPERATING_FIELDS
    if unknown:
        raise KeyError(f"Unknown parameter(s): {sorted(unknown)}")

    design = replace(base_design, **{k: v for k, v in overrides.items() if k in DESIGN_FIELDS})
    op = replace(base_op, **{k: v for k, v in overrides.items() if k in OPERATING_FIELDS})

    geometry_changed = {"outer_diameter_m", "clad_thickness_m"} & set(overrides)
    if geometry_changed and "pellet_diameter_m" not in overrides:
        design = base_design.with_geometry(
            outer_diameter_m=design.outer_diameter_m,
            clad_thickness_m=design.clad_thickness_m,
            gap_m=base_design.radial_gap_m,
        )
        design = replace(design, **{k: v for k, v in overrides.items() if k in DESIGN_FIELDS
                                    and k not in ("outer_diameter_m", "clad_thickness_m", "pellet_diameter_m")})
    if design.pellet_diameter_m <= 0:
        return None
    return design, op


def case_row(design: RodDesign, op: Operating) -> dict:
    """Evaluate one case and return inputs + outputs in a single flat dict.

    `num_rods` in the row is the rod count actually used (see `evaluate`).
    """
    result = evaluate(design, op)
    return {**design.__dict__, **op.__dict__, "burnup_GWd_tHM": resolved_burnup(design, op), **result}


def run_sweep(base_design: RodDesign, base_op: Operating,
              grid: Mapping[str, Sequence]) -> pd.DataFrame:
    """Evaluate every combination in `grid` (a dict of parameter -> list of values)."""
    grid = dict(grid)
    if (base_op.power_mode == "fixed_core_power" and "num_rods" in grid
            and "power_mode" not in grid):
        warnings.warn("num_rods is ignored in fixed_core_power mode (it is recomputed "
                      "from power); dropping it from the sweep.", stacklevel=2)
        grid.pop("num_rods")

    names = list(grid)
    rows = []
    for values in itertools.product(*(grid[n] for n in names)):
        case = build_case(base_design, base_op, dict(zip(names, values)))
        if case is not None:
            rows.append(case_row(*case))
    return pd.DataFrame(rows)
