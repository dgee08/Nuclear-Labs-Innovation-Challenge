"""SMR fuel-rod design explorer (Streamlit front end).

All modelling lives in the `smr` package; this file only collects inputs,
calls it, and shows the results.  Run with:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from smr import plots
from smr.analysis import compare_options, oat_sensitivity, pareto_front
from smr.constants import (
    CLADDING_MATERIALS, FUELS, GUIDE_MATERIALS, NOZZLE_MATERIALS, REF, REF_GAP_M,
    SCENARIOS, SMR_TYPES, SPACER_MATERIALS,
)
from smr.constraints import RULE_LABELS, Limits, check, failed_rules
from smr.cost_model import METRICS, evaluate, metric_label
from smr.models import BWRX300_THERMAL_MW, Operating, RodDesign
from smr.optimize import frange, optimize
from smr.sweep import build_case, case_row, run_sweep

st.set_page_config(page_title="SMR fuel-rod design explorer", layout="wide")

# Columns shown in tables: key -> display name
TABLE_METRICS = {
    "rod_change_interval_yr": "Rod change interval (yrs)",
    "procurement_total_usd": "Core procurement ($)",
    "operational_usd_per_year": "Operational ($/yr)",
    "maintenance_usd_per_year": "Maintenance ($/yr)",
    "lifecycle_usd_per_MWh_th": "Lifecycle $/MWh (thermal)",
    "lifecycle_usd_per_MWh_e": "Lifecycle $/MWh (electric)",
    "procurement_usd_per_MWh_e": "Procurement $/MWh (electric)",
}
PARAM_LABELS = {
    "length_m": "Rod length", "outer_diameter_m": "Rod outer diameter",
    "clad_thickness_m": "Cladding thickness", "capacity_factor": "Capacity factor",
    "core_power_MWt": "Core power", "burnup_GWd_tHM": "Burnup",
}


def money(value: float) -> str:
    return f"${value / 1e6:,.2f}M" if value >= 1e7 else f"${value:,.0f}"


# Cached wrappers: sweeps are the slow part, so repeat runs with the same inputs are free.
@st.cache_data(show_spinner="Running sweep...")
def cached_sweep(design: RodDesign, op: Operating, grid: dict) -> pd.DataFrame:
    return run_sweep(design, op, grid)


@st.cache_data(show_spinner="Searching...")
def cached_optimize(design, op, search, objective, limits):
    return optimize(design, op, search, objective=objective, limits=limits)


# ------------------------------ sidebar inputs ------------------------------
with st.sidebar:
    st.header("Design inputs")
    smr_type = st.selectbox("SMR type", SMR_TYPES)

    st.subheader("Operation")
    scenario = st.selectbox("Cost scenario", SCENARIOS, index=1, format_func=str.title)
    power_mode = st.selectbox(
        "Power model", ["fixed_core_power", "scale_with_N"],
        format_func=lambda m: "Fixed reactor power" if m == "fixed_core_power" else "Power scales with rod count",
        help="In fixed-power mode the rod count is calculated from power, so the rod-count input is not used.")
    capacity_factor = st.slider("Capacity factor", 0.5, 1.0, 0.9)
    core_power = None
    rods = REF["N_rods"]
    if power_mode == "fixed_core_power":
        core_power = st.number_input("Core thermal power (MWt)", 1.0, 5000.0, BWRX300_THERMAL_MW,
                                     help="The BWRX-300 is roughly 870 MWt.")
    else:
        rods = st.number_input("Number of rods", 1, 20000, REF["N_rods"])

    st.subheader("Geometry")
    length = st.number_input("Rod length (m)", 0.5, 6.0, 3.7)
    outer_mm = st.number_input("Rod outer diameter (mm)", 5.0, 50.0, REF["clad_od_m"] * 1e3, format="%.4f")
    clad_mm = st.number_input("Cladding thickness (mm)", 0.1, 2.0, REF["clad_thickness_m"] * 1e3, format="%.4f")

    st.subheader("Materials")
    fuel = st.selectbox("Fuel", FUELS)
    clad_mat = st.selectbox("Cladding", CLADDING_MATERIALS)
    guide_mat = st.selectbox("Guide tube", GUIDE_MATERIALS)
    spacer_mat = st.selectbox("Spacer", SPACER_MATERIALS, index=SPACER_MATERIALS.index("SS316"))
    nozzle_mat = st.selectbox("Nozzle", NOZZLE_MATERIALS)

    with st.expander("Physical limits (placeholder values)"):
        st.caption("Used to flag or filter infeasible designs. These defaults are placeholders: "
                   "replace them with values you can justify.")
        defaults = Limits()
        limits = Limits(
            min_radial_gap_m=st.number_input("Min pellet gap (um)", 0.0, 200.0, defaults.min_radial_gap_m * 1e6) * 1e-6,
            min_clad_thickness_m=st.number_input("Min cladding thickness (mm)", 0.0, 2.0, defaults.min_clad_thickness_m * 1e3) * 1e-3,
            min_rod_change_interval_yr=st.number_input("Min fuel cycle (yrs)", 0.0, 10.0, defaults.min_rod_change_interval_yr),
        )

design = RodDesign(
    length_m=length, num_rods=int(rods), pellet_material=fuel, cladding_material=clad_mat,
    guide_tube_material=guide_mat, spacer_material=spacer_mat, nozzle_material=nozzle_mat, smr_type=smr_type,
).with_geometry(outer_diameter_m=outer_mm * 1e-3, clad_thickness_m=clad_mm * 1e-3, gap_m=REF_GAP_M)
op = Operating(scenario=scenario, power_mode=power_mode, core_power_MWt=core_power, capacity_factor=capacity_factor)

st.title("SMR fuel-rod design explorer")

if design.pellet_diameter_m <= 0:
    st.error("The cladding is too thick for this outer diameter: the pellet would have no room. "
             "Increase the outer diameter or reduce the cladding thickness.")
    st.stop()

tab_design, tab_fuel, tab_sens, tab_opt, tab_space = st.tabs(
    ["Design", "Fuel comparison", "Sensitivity", "Optimizer", "Design space"])

# --------------------------------- Design tab --------------------------------
with tab_design:
    result = evaluate(design, op)
    row = check(pd.DataFrame([case_row(design, op)]), limits).iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Core thermal power", f"{result['core_power_MWt']:.1f} MWt")
    c1.metric("Rod count", f"{result['num_rods']:,}")
    c1.metric("Rod change interval", f"{result['rod_change_interval_yr']:.2f} yrs")
    c2.metric("Core procurement", money(result["procurement_total_usd"]))
    c2.metric("Operational", f"{money(result['operational_usd_per_year'])} / yr")
    c2.metric("Maintenance", f"{money(result['maintenance_usd_per_year'])} / yr")
    c3.metric("Lifecycle $/MWh (thermal)", f"${result['lifecycle_usd_per_MWh_th']:.2f}")
    c3.metric("Lifecycle $/MWh (electric)", f"${result['lifecycle_usd_per_MWh_e']:.2f}")
    c3.metric("Procurement $/MWh (electric)", f"${result['procurement_usd_per_MWh_e']:.2f}")
    st.caption(f"Pellet diameter {design.pellet_diameter_m * 1e3:.3f} mm, "
               f"radial gap {design.radial_gap_m * 1e6:.1f} um.")

    if row["feasible"]:
        st.success("Passes all physical limits.")
    else:
        st.warning("Fails: " + "; ".join(failed_rules(row)) + ".")
    if result["rod_change_interval_yr"] <= 0.25:
        st.info("The model floors the rod change interval at 0.25 years; this design hits that floor.")

    st.plotly_chart(plots.cost_breakdown(result), width="stretch")

# ----------------------------- Fuel comparison tab ----------------------------
with tab_fuel:
    st.caption("Same geometry, materials and operation; only the fuel changes.")
    fuel_df = compare_options(design, op, "pellet_material", FUELS)
    st.dataframe(fuel_df[["pellet_material", *TABLE_METRICS]].rename(
        columns={"pellet_material": "Fuel", **TABLE_METRICS}), hide_index=True)
    metric = st.selectbox("Chart metric", list(TABLE_METRICS), index=5,
                          format_func=TABLE_METRICS.get, key="fuel_metric")
    st.plotly_chart(plots.grouped_bars(fuel_df, "pellet_material", metric), width="stretch")

# ------------------------------ Sensitivity tab -------------------------------
with tab_sens:
    st.caption("Moves each input up and down by the same percentage, one at a time, and shows how a "
               "metric responds. An input with a tiny bar is one the model barely reacts to.")
    s1, s2 = st.columns(2)
    sens_metric = s1.selectbox("Metric", list(METRICS)[:6], format_func=metric_label, key="sens_metric")
    rel = s2.slider("Change in each input", 0.05, 0.5, 0.2, 0.05, format="%.2f")
    sens = oat_sensitivity(design, op, metric=sens_metric, rel_change=rel)
    st.plotly_chart(plots.tornado(sens, sens_metric, rel), width="stretch")
    st.dataframe(sens.assign(parameter=sens["parameter"].map(lambda p: PARAM_LABELS.get(p, p)))
                 [["parameter", "base_value", "delta_low_pct", "delta_high_pct", "swing_pct"]],
                 hide_index=True)

# -------------------------------- Optimizer tab -------------------------------
with tab_opt:
    st.caption("Grid search over the ranges below, keeping everything else as set in the sidebar.")
    o1, o2 = st.columns(2)
    od_lo = o1.number_input("Min outer diameter (mm)", 5.0, 20.0, 8.0)
    od_hi = o2.number_input("Max outer diameter (mm)", 5.0, 20.0, 12.0)
    od_step = o1.number_input("Diameter step (mm)", 0.05, 2.0, 0.5)
    search = {"outer_diameter_m": frange(od_lo * 1e-3, od_hi * 1e-3, od_step * 1e-3)}
    if power_mode == "scale_with_N":
        r_lo = o2.number_input("Min rods", 50, 2000, 100)
        r_hi = o2.number_input("Max rods", 50, 2000, 600)
        search["num_rods"] = list(range(int(r_lo), int(r_hi) + 1, 20))
    else:
        st.caption("Rod count is not searched: in fixed-power mode it is set by power and rod length.")

    obj = st.selectbox("Minimise", ["lifecycle_usd_per_MWh_th", "lifecycle_usd_per_MWh_e", "procurement_usd_per_MWh_e"],
                       format_func=metric_label)
    use_limits = st.checkbox("Apply physical limits", value=True)

    if od_lo >= od_hi:
        st.error("Minimum diameter must be smaller than maximum diameter.")
    elif st.button("Run optimizer", type="primary"):
        res = cached_optimize(design, op, search, obj, limits if use_limits else None)
        if res.best is None:
            st.error("No design in this range meets the physical limits.")
        else:
            best = res.best
            st.success(f"Evaluated {res.n_evaluated} designs, {res.n_feasible} feasible.")
            overrides = {k: best[k] for k in search}
            tuned = build_case(design, op, overrides)
            before, after = evaluate(design, op), evaluate(*tuned)
            comp = pd.DataFrame([{
                "Metric": name, "Unoptimized": before[key], "Optimized": after[key],
                "Change (%)": (after[key] / before[key] - 1) * 100 if before[key] else 0.0,
            } for key, name in TABLE_METRICS.items()])
            st.write(f"Best outer diameter: **{best['outer_diameter_m'] * 1e3:.2f} mm**"
                     + (f", rods: **{int(best['num_rods'])}**" if "num_rods" in search else ""))
            if best["outer_diameter_m"] in (search["outer_diameter_m"][0], search["outer_diameter_m"][-1]):
                st.info("The best design sits on the edge of the search range, so the model is pushing "
                        "against a bound. Widen the range or add a constraint that explains the limit.")
            st.dataframe(comp, hide_index=True,
                         column_config={c: st.column_config.NumberColumn(format="%.2f")
                                        for c in ("Unoptimized", "Optimized", "Change (%)")})
            st.plotly_chart(plots.scatter(res.table, "outer_diameter_m", obj,
                                          color="feasible" if use_limits else None), width="stretch")

# ------------------------------ Design space tab ------------------------------
with tab_space:
    st.caption("Sweep fuels, cladding and geometry, drop designs that break the physical limits, "
               "then look for trade-offs.")
    sp1, sp2 = st.columns(2)
    fuels_sel = sp1.multiselect("Fuels", FUELS, default=["UO2", "MOX"])
    clads_sel = sp2.multiselect("Cladding", CLADDING_MATERIALS, default=["Zircaloy", "SS316", "Inconel"])
    od_rng = sp1.slider("Outer diameter (mm)", 6.0, 16.0, (8.0, 12.0), 0.5)
    t_rng = sp2.slider("Cladding thickness (mm)", 0.2, 1.2, (0.4, 0.8), 0.1)
    scen_sel = sp1.multiselect("Cost scenarios", SCENARIOS, default=["mean"])

    if fuels_sel and clads_sel and scen_sel:
        grid = {
            "pellet_material": fuels_sel, "cladding_material": clads_sel, "scenario": scen_sel,
            "outer_diameter_m": frange(od_rng[0] * 1e-3, od_rng[1] * 1e-3, 0.5e-3),
            "clad_thickness_m": frange(t_rng[0] * 1e-3, t_rng[1] * 1e-3, 0.1e-3),
        }
        sweep_df = check(cached_sweep(design, op, grid), limits)
        sweep_df["outer_diameter_mm"] = sweep_df["outer_diameter_m"] * 1e3
        sweep_df["clad_thickness_mm"] = sweep_df["clad_thickness_m"] * 1e3
        n_ok = int(sweep_df["feasible"].sum())
        st.write(f"{len(sweep_df):,} designs evaluated, {n_ok:,} pass the physical limits.")

        show_infeasible = st.checkbox("Show designs that fail the limits", value=False)
        view = sweep_df if show_infeasible else sweep_df[sweep_df["feasible"]]
        if view.empty:
            st.warning("No designs to show: every combination fails the physical limits.")
        else:
            axes = list(METRICS)[:4]
            a1, a2, a3 = st.columns(3)
            x_key = a1.selectbox("X axis", axes, index=3, format_func=metric_label)
            y_key = a2.selectbox("Y axis", axes, index=0, format_func=metric_label)
            color_by = a3.selectbox("Colour by", ["pellet_material", "cladding_material", "scenario", "feasible"])
            sense = {"lifecycle_usd_per_MWh_e": "min", "lifecycle_usd_per_MWh_th": "min",
                     "procurement_usd_per_MWh_e": "min", "rod_change_interval_yr": "max"}
            front = pareto_front(view, {x_key: sense[x_key], y_key: sense[y_key]}) if x_key != y_key else None
            st.plotly_chart(plots.scatter(view, x_key, y_key, color=color_by, front=front,
                                          hover=["pellet_material", "cladding_material",
                                                 "outer_diameter_mm", "clad_thickness_mm"]),
                            width="stretch")
            if front is not None:
                st.caption(f"{int(front.sum())} design(s) on the Pareto front "
                           "(no other design is at least as good on both axes). "
                           "A front with a single point means the two goals are not in tension in this model.")

            hm1, hm2 = st.columns(2)
            hm_z = hm1.selectbox("Heatmap value", axes, format_func=metric_label, key="hm_z")
            st.plotly_chart(plots.heatmap(view, "outer_diameter_mm", "clad_thickness_mm", hm_z),
                            width="stretch")

        st.download_button("Download sweep as CSV", sweep_df.to_csv(index=False), "sweep.csv", "text/csv")
    else:
        st.info("Pick at least one fuel, cladding material and cost scenario.")
