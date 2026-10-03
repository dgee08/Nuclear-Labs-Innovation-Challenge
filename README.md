# SMR fuel-rod design explorer

A cleaned-up rewrite of the supplied SMR Reactor Design Optimization Tool. The cost
arithmetic is unchanged (verified against the original on thousands of random
designs); the structure is new so that sweeps, sensitivity analysis, constraints and
plots are easy to build on.

## Run it

    pip install -r requirements.txt
    streamlit run app.py          # interactive app
    python scripts/run_sweep.py   # writes data/sweep.csv for pandas / Power BI
    pytest -q                     # 25 tests

## Layout

    smr/constants.py    reference rod, cost tables, materials (all assumptions in one place)
    smr/models.py       RodDesign (what you build) and Operating (how you run it)
    smr/cost_model.py   evaluate(design, op) -> flat dict with units in the key names
    smr/constraints.py  physical feasibility checks; do not change the cost numbers
    smr/sweep.py        run_sweep(design, op, {param: [values]}) -> tidy DataFrame
    smr/analysis.py     oat_sensitivity (tornado), compare_options, pareto_front
    smr/optimize.py     constrained grid search built on run_sweep
    smr/plots.py        Plotly figure builders (usable in notebooks)
    app.py              Streamlit UI: Design, Fuel comparison, Sensitivity, Optimizer, Design space
    tests/              regression tests against the original model + behaviour tests

## Notebook example

    from smr.models import RodDesign, Operating
    from smr.sweep import run_sweep
    from smr.analysis import pareto_front

    df = run_sweep(RodDesign(), Operating(), {
        "pellet_material": ["UO2", "MOX"],
        "outer_diameter_m": [0.009, 0.010, 0.011],
        "scenario": ["low", "mean", "high"],
    })
    df.groupby("pellet_material")["lifecycle_usd_per_MWh_e"].describe()

Every sweep row holds the inputs and the outputs, so any column can go on any axis.
`num_rods` in a row is the rod count actually used.

## Things to know about the model (found while refactoring)

1. **Fixed-power mode ignores the rod-count input.** Rod count is recomputed from power
   and rod length. The original optimizer searched rod counts anyway, which did nothing.
   The new sweep warns and drops that axis; the app only shows it in scale-with-N mode.
2. **Rod length, capacity factor and core power barely affect $/MWh.** Check the
   Sensitivity tab; they matter for fuel-cycle length and totals, not unit cost.
3. **Optimizers run to the edge of the search range.** Larger diameter always looks
   cheaper, because nothing in the model penalises a bigger pellet. The Optimizer tab
   warns when the best design sits on a bound.
4. **Cost and fuel lifetime are not in tension here.** On the default sweep the Pareto
   front collapses to one design (UO2, SS316 cladding, thinnest allowed, widest rod),
   since SS316 is cheapest and the model has no neutron-absorption penalty. A real
   trade-off needs missing physics added.
5. **The rod change interval is floored at 0.25 years.** TRISO in a light-water setup
   hits the floor.
6. Back-end costs use the UO2 numbers for every fuel, and thermal-to-electric
   efficiency is 0.33 for every reactor type.

## Where to extend

- Replace the placeholder limits in `smr/constraints.py` with justified values, and add
  rules (heat flux, fuel temperature, fuel/reactor compatibility, neutron absorption).
- Add a second objective that competes with cost, then rerun the Pareto analysis.
- Use `data/sweep.csv` as the source for a Power BI dashboard.
