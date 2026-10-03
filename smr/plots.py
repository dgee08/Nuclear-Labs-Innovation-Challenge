"""Plotly figure builders.  No Streamlit here, so they work in notebooks too."""
from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .cost_model import metric_label

TEMPLATE = "plotly_white"
PALETTE = px.colors.qualitative.Safe


def cost_breakdown(result: Mapping[str, float]) -> go.Figure:
    """Where the lifecycle cost goes: front end, fabrication, hardware, back end."""
    parts = {
        "Front end (mining to enrichment)": result["cost_front_end_usd"],
        "Fabrication": result["cost_fabrication_usd"],
        "Hardware (cladding, structure)": result["cost_hardware_usd"],
        "Back end (storage, disposal)": result["cost_back_end_usd"],
    }
    fig = go.Figure(go.Bar(
        x=list(parts.values()), y=list(parts), orientation="h",
        marker_color=PALETTE[: len(parts)],
        text=[f"${v / 1e6:,.1f}M" for v in parts.values()], textposition="outside",
    ))
    fig.update_layout(template=TEMPLATE, title="Lifecycle cost breakdown", height=300,
                      xaxis_title="$", yaxis=dict(autorange="reversed"),
                      margin=dict(l=10, r=40, t=50, b=40))
    return fig


def grouped_bars(df: pd.DataFrame, x: str, y: str, color: Optional[str] = None) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, barmode="group", template=TEMPLATE,
                 color_discrete_sequence=PALETTE, labels={y: metric_label(y)})
    fig.update_layout(height=380)
    return fig


def tornado(sens: pd.DataFrame, metric: str, rel_change: float) -> go.Figure:
    """Tornado chart from `analysis.oat_sensitivity` output."""
    s = sens.iloc[::-1]  # largest swing on top
    fig = go.Figure()
    fig.add_bar(y=s["parameter"], x=s["delta_low_pct"], orientation="h",
                name=f"Input -{rel_change:.0%}", marker_color=PALETTE[0])
    fig.add_bar(y=s["parameter"], x=s["delta_high_pct"], orientation="h",
                name=f"Input +{rel_change:.0%}", marker_color=PALETTE[1])
    fig.update_layout(template=TEMPLATE, barmode="relative", height=380,
                      title=f"Effect on {metric_label(metric)}",
                      xaxis_title="Change from base design (%)",
                      legend=dict(orientation="h", y=-0.2))
    return fig


def scatter(df: pd.DataFrame, x: str, y: str, color: Optional[str] = None,
            front: Optional[pd.Series] = None, hover: Optional[list] = None) -> go.Figure:
    """Scatter of a sweep.  If `front` (bool mask) is given, the Pareto front is drawn as a line."""
    fig = px.scatter(df, x=x, y=y, color=color, hover_data=hover, template=TEMPLATE,
                     color_discrete_sequence=PALETTE, opacity=0.7,
                     labels={x: metric_label(x), y: metric_label(y)})
    if front is not None and front.any():
        f = df[front].sort_values(x)
        fig.add_trace(go.Scatter(x=f[x], y=f[y], mode="lines+markers", name="Pareto front",
                                 line=dict(color="black", width=2), marker=dict(size=8, color="black")))
    fig.update_layout(height=480)
    return fig


def heatmap(df: pd.DataFrame, x: str, y: str, z: str, aggfunc: str = "mean") -> go.Figure:
    grid = df.pivot_table(index=y, columns=x, values=z, aggfunc=aggfunc)
    fig = go.Figure(go.Heatmap(z=grid.values, x=grid.columns, y=grid.index,
                               colorbar=dict(title=metric_label(z)), colorscale="Viridis"))
    fig.update_layout(template=TEMPLATE, height=480, xaxis_title=metric_label(x),
                      yaxis_title=metric_label(y))
    return fig
