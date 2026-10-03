"""Run a design-space sweep from the command line and save it for later analysis.

    python scripts/run_sweep.py            # writes data/sweep.csv
Open the CSV in pandas, Power BI, or the notebook of your choice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smr.analysis import pareto_front
from smr.constants import CLADDING_MATERIALS, FUELS, SCENARIOS
from smr.constraints import Limits, check
from smr.models import Operating, RodDesign
from smr.optimize import frange
from smr.sweep import run_sweep

GRID = {
    "pellet_material": FUELS,
    "cladding_material": CLADDING_MATERIALS,
    "scenario": SCENARIOS,
    "outer_diameter_m": frange(0.008, 0.012, 0.0005),
    "clad_thickness_m": frange(0.0004, 0.0008, 0.0001),
}

if __name__ == "__main__":
    df = check(run_sweep(RodDesign(), Operating(), GRID), Limits())
    df["pareto"] = False
    feas = df[df["feasible"] & (df["scenario"] == "mean")]
    df.loc[feas.index, "pareto"] = pareto_front(
        feas, {"lifecycle_usd_per_MWh_e": "min", "rod_change_interval_yr": "max"})
    out = Path(__file__).resolve().parents[1] / "data" / "sweep.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"{len(df)} rows ({int(df['feasible'].sum())} feasible, "
          f"{int(df['pareto'].sum())} on the Pareto front) -> {out}")
