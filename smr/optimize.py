"""Constrained grid-search optimizer built on `run_sweep`."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from .constraints import Limits, check
from .models import Operating, RodDesign
from .sweep import run_sweep


def frange(start: float, stop: float, step: float) -> list[float]:
    """Inclusive float range (np.arange without the end-point surprises)."""
    n = int(round((stop - start) / step)) + 1
    return [float(v) for v in start + step * np.arange(max(n, 1))]


@dataclass
class OptimizationResult:
    best: Optional[pd.Series]   # best feasible row, or None if nothing is feasible
    table: pd.DataFrame         # every evaluated row, with feasibility columns
    objective: str
    n_evaluated: int
    n_feasible: int


def optimize(base_design: RodDesign, base_op: Operating,
             search: Mapping[str, Sequence],
             objective: str = "lifecycle_usd_per_MWh_th",
             sense: str = "min",
             limits: Optional[Limits] = Limits()) -> OptimizationResult:
    """Grid-search `search` and return the best row that satisfies `limits`.

    Pass limits=None to optimize with no physical constraints (useful for
    showing what an unconstrained optimizer does).
    """
    table = run_sweep(base_design, base_op, search)
    if table.empty:
        return OptimizationResult(None, table, objective, 0, 0)

    if limits is not None:
        table = check(table, limits)
        candidates = table[table["feasible"]]
    else:
        table = table.assign(feasible=True)
        candidates = table

    best = None
    if not candidates.empty:
        idx = candidates[objective].idxmin() if sense == "min" else candidates[objective].idxmax()
        best = table.loc[idx]
    return OptimizationResult(best, table, objective, len(table), len(candidates))
