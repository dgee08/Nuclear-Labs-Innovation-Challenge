"""Physical feasibility checks.

The cost model knows nothing about physics, so an optimizer left alone will
happily pick designs that cannot be built (a pellet wider than its cladding,
paper-thin cladding, fuel that must be swapped every few weeks).  These checks
sit *beside* the cost model: they never change its numbers, they only flag or
filter designs.

IMPORTANT: the default limits below are PLACEHOLDERS chosen to be plausible,
not validated values.  Replace them with numbers your science teammate can
justify (and cite) -- that justification is the science half of the project.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Limits:
    min_radial_gap_m: float = 40e-6          # pellet must fit inside cladding with room to swell
    min_clad_thickness_m: float = 0.40e-3    # strength / corrosion allowance (placeholder)
    min_rod_change_interval_yr: float = 1.0  # shortest practical fuel cycle (placeholder)


RULE_LABELS = {
    "gap_ok": "Pellet fits inside cladding",
    "clad_thickness_ok": "Cladding thick enough",
    "interval_ok": "Fuel cycle long enough",
}


def check(df: pd.DataFrame, limits: Limits = Limits()) -> pd.DataFrame:
    """Return `df` with one boolean column per rule plus `feasible`.

    Needs the columns outer_diameter_m, pellet_diameter_m, clad_thickness_m and
    rod_change_interval_yr (all present in `run_sweep` output).
    """
    out = df.copy()
    gap = (out["outer_diameter_m"] - 2.0 * out["clad_thickness_m"] - out["pellet_diameter_m"]) / 2.0
    out["radial_gap_m"] = gap
    out["gap_ok"] = gap >= limits.min_radial_gap_m
    out["clad_thickness_ok"] = out["clad_thickness_m"] >= limits.min_clad_thickness_m
    out["interval_ok"] = out["rod_change_interval_yr"] >= limits.min_rod_change_interval_yr
    out["feasible"] = out[list(RULE_LABELS)].all(axis=1)
    return out


def failed_rules(row: pd.Series) -> list[str]:
    """Human-readable list of the rules a single checked row violates."""
    return [label for key, label in RULE_LABELS.items() if not bool(row[key])]
