"""Run with:  pytest -q"""
import json
import math
import warnings
from pathlib import Path

import pandas as pd
import pytest

from smr import constants as c
from smr.analysis import oat_sensitivity, pareto_front
from smr.constraints import Limits, check
from smr.cost_model import evaluate
from smr.models import Operating, RodDesign
from smr.optimize import frange, optimize
from smr.sweep import build_case, run_sweep

GOLDEN = json.loads((Path(__file__).parent / "golden.json").read_text())["cases"]


@pytest.mark.parametrize("case", GOLDEN)
def test_matches_original_model(case):
    """The refactor must not change any numbers produced by the original model.py."""
    result = evaluate(RodDesign(**case["design"]), Operating(**case["operating"]))
    for key, expected in case["expected"].items():
        assert result[key] == pytest.approx(expected, rel=1e-9), key


def test_mox_proxy_is_calibrated_to_paper_anchor():
    m = c.REF["kgU_per_rod"]
    backend = sum(c.WIT_UO2[k]["mean"] for k in c.BACKEND_KEYS) * m
    fab = c.WIT_MOX["fabrication"]["mean"] * m
    proxy = c.WIT_MOX["reprocessing_proxy"]["mean"]
    assert (backend + fab + proxy * m) == pytest.approx(c.MOX_LIFECYCLE_ANCHOR_USD_PER_ROD)


def test_cost_breakdown_adds_up():
    r = evaluate(RodDesign(), Operating())
    assert r["cost_front_end_usd"] + r["cost_fabrication_usd"] + r["cost_hardware_usd"] == pytest.approx(r["procurement_total_usd"])
    assert r["procurement_total_usd"] + r["cost_back_end_usd"] == pytest.approx(r["lifecycle_total_usd"])


def test_fixed_power_ignores_input_rod_count():
    a = evaluate(RodDesign(num_rods=10), Operating())
    b = evaluate(RodDesign(num_rods=9999), Operating())
    assert a["num_rods"] == b["num_rods"]


def test_sweep_drops_rod_axis_in_fixed_power_mode():
    with pytest.warns(UserWarning):
        df = run_sweep(RodDesign(), Operating(), {"num_rods": [100, 200]})
    assert len(df) == 1


def test_geometry_override_keeps_radial_gap():
    base = RodDesign()
    design, _ = build_case(base, Operating(), {"outer_diameter_m": 0.011})
    assert design.radial_gap_m == pytest.approx(base.radial_gap_m)


def test_impossible_geometry_is_skipped():
    assert build_case(RodDesign(), Operating(), {"clad_thickness_m": 0.01}) is None


def test_unknown_parameter_raises():
    with pytest.raises(KeyError):
        build_case(RodDesign(), Operating(), {"not_a_parameter": 1})


def test_reference_design_passes_default_limits():
    df = check(run_sweep(RodDesign(), Operating(), {"scenario": ["mean"]}), Limits())
    assert bool(df["feasible"].iloc[0])


def test_constraints_flag_oversized_pellet():
    row = pd.DataFrame([{"outer_diameter_m": 0.0095, "pellet_diameter_m": 0.0090,
                         "clad_thickness_m": 0.0006, "rod_change_interval_yr": 3.0}])
    assert not check(row).iloc[0]["gap_ok"]


def test_pareto_front_basic():
    df = pd.DataFrame({"cost": [1, 2, 3, 2], "life": [1, 3, 5, 1]})
    mask = pareto_front(df, {"cost": "min", "life": "max"})
    assert mask.tolist() == [True, True, True, False]  # (2, 1) is dominated by (1, 1)


def test_sensitivity_sorted_and_finds_inert_input():
    s = oat_sensitivity(RodDesign(), Operating())
    assert s["swing_pct"].is_monotonic_decreasing
    # Rod length barely matters to $/MWh in fixed-power mode (rod count rescales to compensate).
    assert s.set_index("parameter").loc["length_m", "swing_pct"] < 0.01


def test_optimizer_respects_limits():
    # Force a limit that excludes thin cladding; the winner must satisfy it.
    res = optimize(RodDesign(), Operating(), {"clad_thickness_m": frange(0.0003, 0.0009, 0.0001)},
                   limits=Limits(min_clad_thickness_m=0.0006))
    assert res.best["clad_thickness_m"] >= 0.0006 - 1e-12
    assert res.n_feasible < res.n_evaluated


def test_optimizer_returns_none_when_nothing_feasible():
    res = optimize(RodDesign(), Operating(), {"outer_diameter_m": [0.009]},
                   limits=Limits(min_rod_change_interval_yr=1000))
    assert res.best is None
