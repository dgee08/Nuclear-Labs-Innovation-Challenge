"""SMR fuel-rod design explorer.

Layers (each only imports from the ones above it):

    constants    -> reference geometry, cost tables, material properties
    models       -> RodDesign / Operating dataclasses
    cost_model   -> evaluate(design, operating) -> flat result dict
    constraints  -> physical feasibility checks (opt-in, does not change costs)
    sweep        -> run_sweep(): many evaluations -> tidy DataFrame
    analysis     -> sensitivity (tornado) and Pareto-front helpers
    optimize     -> constrained grid search built on sweep
    plots        -> Plotly figure builders (no Streamlit imports)

The Streamlit app (app.py) only wires inputs to these functions and shows
the figures, so everything here can also be used from a notebook or script.
"""
