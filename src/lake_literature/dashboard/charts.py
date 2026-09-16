"""Figure builders shared by every dashboard page.

Each function returns a styled `plotly.graph_objects.Figure` ready to be
passed to `components.render_chart`. Centralizing these collapses the
near-identical charts that used to be copy-pasted across pages (top-N bars,
source-split bars/lines, stacked areas) into one implementation each.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from lake_literature.dashboard.theme import (
    CATEGORICAL_PALETTE,
    OTHER_COLOR,
    SOURCE_COLORS,
    SOURCE_LABELS,
    TOTAL_COLOR,
    TOTAL_LABEL,
    hex_to_rgba,
    polish_figure_layout,
)


def source_bars(
    df: pd.DataFrame,
    x: str,
    *,
    title: str | None = None,
    total_line: bool = False,
    labels: dict[str, str] | None = None,
) -> go.Figure:
    """Stacked IEEE/Elsevier bars, with an optional real Total line on top.

    `df` must have the shape produced by `analytics.source_counts_by`:
    columns `[x, "ieee", "elsevier", "total"]`.
    """
    fig = go.Figure()
    fig.add_bar(
        x=df[x], y=df["ieee"], name=SOURCE_LABELS["ieee"], marker_color=SOURCE_COLORS["ieee"]
    )
    fig.add_bar(
        x=df[x],
        y=df["elsevier"],
        name=SOURCE_LABELS["elsevier"],
        marker_color=SOURCE_COLORS["elsevier"],
    )
    fig.update_layout(barmode="stack", title=title)
    if total_line:
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df["total"],
                name=TOTAL_LABEL,
                mode="lines+markers",
                line=dict(color=TOTAL_COLOR, width=2, dash="solid"),
                marker=dict(size=5),
            )
        )
    if labels:
        fig.update_layout(xaxis_title=labels.get(x, x), yaxis_title=labels.get("value"))
    polish_figure_layout(fig)
    return fig


def source_lines(
    df: pd.DataFrame,
    x: str,
    *,
    title: str | None = None,
    y_title: str | None = None,
    spline: bool = False,
    fill: bool = False,
) -> go.Figure:
    """Three real line traces -- IEEE, Elsevier, and Total -- over `x`.

    `df` must have columns `[x, "ieee", "elsevier", "total"]`, e.g. from
    `analytics.cumulative_by_source` or `analytics.source_counts_by`.

    `spline=True` smooths the lines. `fill=True` shades the area under a
    source's line down to zero, but only when exactly one of IEEE/Elsevier
    is actually present in `df` (e.g. the sidebar is filtered to one source)
    -- filling both at once would just overlap two translucent regions with
    no added meaning.
    """
    line_shape = "spline" if spline else "linear"
    active_sources = [src for src in ("ieee", "elsevier") if df[src].sum() > 0]
    fill_single_source = fill and len(active_sources) == 1

    fig = go.Figure()
    for src in ("ieee", "elsevier"):
        line_kwargs: dict = {"x": df[x], "y": df[src], "mode": "lines+markers"}
        if fill_single_source and src in active_sources:
            line_kwargs["fill"] = "tozeroy"
            line_kwargs["fillcolor"] = hex_to_rgba(SOURCE_COLORS[src], 0.2)
        fig.add_trace(
            go.Scatter(
                name=SOURCE_LABELS[src],
                line=dict(color=SOURCE_COLORS[src], width=2, shape=line_shape),
                marker=dict(size=5),
                **line_kwargs,
            )
        )
    fig.add_trace(
        go.Scatter(
            x=df[x],
            y=df["total"],
            name=TOTAL_LABEL,
            mode="lines+markers",
            line=dict(color=TOTAL_COLOR, width=2.5, shape=line_shape),
            marker=dict(size=6),
        )
    )
    fig.update_layout(title=title, yaxis_title=y_title)
    polish_figure_layout(fig)
    return fig


def topn_hbar(
    series: pd.Series,
    *,
    color_by: pd.Series | None = None,
    palette: dict[str, str] | None = None,
    title: str | None = None,
    x_title: str | None = None,
) -> go.Figure:
    """Top-N horizontal bar chart, optionally colored by a categorical series.

    `series` is indexed by category label, valued by the metric to rank on
    (already sorted/head-limited by the caller). `color_by`, if given, must
    share `series`'s index (e.g. the modal source per venue/author).
    """
    ordered = series.sort_values(ascending=True)
    df = pd.DataFrame({"label": ordered.index, "value": ordered.values})
    if color_by is not None:
        df["color"] = color_by.reindex(ordered.index).values
        color_map = palette or SOURCE_COLORS
        fig = px.bar(
            df,
            x="value",
            y="label",
            color="color",
            orientation="h",
            color_discrete_map=color_map,
            labels={"value": x_title or "", "label": "", "color": "Base"},
        )
    else:
        fig = px.bar(
            df,
            x="value",
            y="label",
            orientation="h",
            labels={"value": x_title or "", "label": ""},
            color_discrete_sequence=[CATEGORICAL_PALETTE[0]],
        )
    fig.update_layout(title=title, showlegend=color_by is not None)
    polish_figure_layout(fig)
    return fig


def stacked_area(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    color: str,
    color_map: dict[str, str] | None = None,
    category_orders: dict[str, list[str]] | None = None,
    title: str | None = None,
    groupnorm: str | None = None,
) -> go.Figure:
    """Stacked area chart, e.g. cumulative composition by venue/keyword.

    `groupnorm="percent"` turns this into a 100%-stacked area (used by the
    topic-share trend chart). `category_orders` (a px constructor argument,
    not a `fig.update_layout` kwarg) controls stacking/legend order.
    """
    fig = px.area(
        df,
        x=x,
        y=y,
        color=color,
        color_discrete_map=color_map,
        category_orders=category_orders,
        groupnorm=groupnorm,
    )
    if color_map and OTHER_COLOR not in color_map.values():
        pass  # caller is responsible for including the "Others" bucket color
    fig.update_layout(title=title)
    polish_figure_layout(fig)
    return fig
