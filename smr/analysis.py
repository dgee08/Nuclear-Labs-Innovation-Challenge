"""Sensitivity analysis and Pareto-front helpers."""
from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .cost_model import evaluate, resolved_burnup
from .models import Operating, RodDesign
from .sweep import DESIGN_FIELDS, build_case

DEFAULT_NUMERIC_PARAMS = (
    "length_m", "outer_diameter_m", "clad_thickness_m",
    "capacity_factor", "core_power_MWt", "burnup_GWd_tHM",
)


def _base_value(design: RodDesign, op: Operating, name: str):
    if name == "burnup_GWd_tHM":
        return resolved_burnup(design, op)
    return getattr(design if name in DESIGN_FIELDS else op, name)


def oat_sensitivity(base_design: RodDesign, base_op: Operating,
                    metric: str = "lifecycle_usd_per_MWh_e",
                    params: Sequence[str] = DEFAULT_NUMERIC_PARAMS,
                    rel_change: float = 0.2) -> pd.DataFrame:
    """One-at-a-time sensitivity: move each input by +/- rel_change, hold the rest.

    Returns one row per input, sorted by swing (largest effect first).  An input
    with ~0 swing is one the model barely responds to.  Interactions between
    inputs are NOT captured; use a sweep + regression for that.
    """
    base_metric = evaluate(base_design, base_op)[metric]
    rows = []
    for name in params:
        base = _base_value(base_design, base_op, name)
        if base is None:  # e.g. core power in scale_with_N mode
            continue
        lo, hi = base * (1 - rel_change), base * (1 + rel_change)
        if name == "capacity_factor":
            hi = min(hi, 1.0)
        vals = []
        for v in (lo, hi):
            case = build_case(base_design, base_op, {name: v})
            vals.append(np.nan if case is None else evaluate(*case)[metric])
        rows.append({
            "parameter": name, "base_value": base, "low_value": lo, "high_value": hi,
            "metric_at_low": vals[0], "metric_at_high": vals[1], "base_metric": base_metric,
            "delta_low_pct": (vals[0] / base_metric - 1) * 100,
            "delta_high_pct": (vals[1] / base_metric - 1) * 100,
        })
    out = pd.DataFrame(rows)
    out["swing_pct"] = (out["delta_high_pct"] - out["delta_low_pct"]).abs()
    return out.sort_values("swing_pct", ascending=False).reset_index(drop=True)


def compare_options(base_design: RodDesign, base_op: Operating,
                    param: str, options: Sequence) -> pd.DataFrame:
    """Evaluate the base case once per option of one parameter (e.g. each fuel)."""
    from .sweep import case_row
    rows = []
    for option in options:
        case = build_case(base_design, base_op, {param: option})
        if case is not None:
            rows.append(case_row(*case))
    return pd.DataFrame(rows)


def pareto_front(df: pd.DataFrame, objectives: Mapping[str, str]) -> pd.Series:
    """Boolean mask of non-dominated rows.

    objectives maps column -> "min" or "max".  A row is on the front if no other
    row is at least as good on every objective and strictly better on one.
    Rows with missing values are never on the front.  O(n^2) worst case; fine
    for tens of thousands of rows.
    """
    cols = list(objectives)
    sign = np.array([1.0 if objectives[c] == "min" else -1.0 for c in cols])
    X = df[cols].to_numpy(dtype=float) * sign
    valid = ~np.isnan(X).any(axis=1)
    efficient = valid.copy()
    for i in np.flatnonzero(valid):
        if not efficient[i]:
            continue
        dominated_by_i = np.all(X[i] <= X, axis=1) & np.any(X[i] < X, axis=1)
        efficient[dominated_by_i] = False
    return pd.Series(efficient, index=df.index, name="pareto")
