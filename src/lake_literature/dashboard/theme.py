"""Colors and small chart helpers shared by every dashboard page.

Keeping these in one module is what makes IEEE blue mean IEEE on every page,
and keeps the venue/categorical palettes from drifting apart over time.
"""

from __future__ import annotations

import logging

import streamlit as st

logger = logging.getLogger(__name__)

# Brand colors -- IEEE blue and Elsevier orange, from each publisher's own brand
# guidelines. Used everywhere a chart breaks down by source, so the same two
# colors always mean the same two publishers across the whole app.
SOURCE_COLORS = {"ieee": "#00629B", "elsevier": "#FF6C00"}
SOURCE_LABELS = {"ieee": "IEEE", "elsevier": "Elsevier"}

# Validated categorical palette (dataviz skill's default 8-slot theme) for charts
# that distinguish many sub-categories within one source (e.g. venues) -- a
# monochromatic brand-color ramp is the wrong tool there (low contrast between
# shades of the same hue); this fixed, CVD-checked order is deliberately NOT
# derived from SOURCE_COLORS. "Others" (the catch-all bucket) always gets a
# neutral gray instead of a palette slot -- it isn't a real category.
CATEGORICAL_PALETTE = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
    "#e34948",
]
OTHER_COLOR = "#9a9a94"

# Diverging pair for growth/decline charts -- deliberately not the brand colors,
# which carry publisher meaning everywhere else.
TREND_UP_COLOR = "#1baf7a"
TREND_DOWN_COLOR = "#4a3aa7"

# "Total" needs to visually pop against both IEEE blue and Elsevier orange on
# every chart that shows all three series together -- a neutral gray used to
# sit here and nearly disappeared next to the two saturated brand colors.
TOTAL_COLOR = "#ff2e77"
TOTAL_LABEL = "Total"

CHART_HEIGHT = 420  # consistent height for side-by-side chart pairs

# ---------------------------------------------------------------------------
# Light/dark tokens
#
# Streamlit's own light/dark toggle (hamburger menu -> Settings -> Theme, or
# "Use system setting") is read at runtime via `st.context.theme.type`, which
# reflects the *active* theme for the current browser session. Our custom CSS
# and every Plotly figure key off the same value, so switching to "Light" in
# Streamlit actually turns the page light instead of leaving the injected
# dark-navy background in place.
# ---------------------------------------------------------------------------

_DARK_TOKENS = {
    "bg_top": "#07131f",
    "bg_mid": "#0b1725",
    "bg_bottom": "#0f1d2b",
    "sidebar_bg": "rgba(10, 18, 28, 0.95)",
    "border": "rgba(148, 163, 184, 0.18)",
    "text": "#e5eefb",
    "muted": "#a5b7d5",
    "accent": "#5ea9ff",
    "input_bg": "rgba(17, 24, 39, 0.9)",
    "input_border": "rgba(148, 163, 184, 0.2)",
    "metric_bg": "linear-gradient(135deg, rgba(12, 46, 75, 0.96), rgba(18, 78, 140, 0.72))",
    "metric_border": "rgba(94, 169, 255, 0.24)",
    "metric_label": "#d7e8ff",
    "metric_value": "#f8fbff",
    "table_bg": "linear-gradient(180deg, rgba(12, 28, 38, 0.98), rgba(16, 31, 45, 0.94))",
    "table_border": "rgba(94, 169, 255, 0.25)",
    "expander_bg": "linear-gradient(180deg, rgba(14, 31, 44, 0.95), rgba(19, 38, 54, 0.92))",
    "button_bg": "linear-gradient(135deg, rgba(94,169,255,0.18), rgba(17,24,39,0.9))",
    "button_border": "rgba(94,169,255,0.28)",
    "tab_bg": "rgba(12, 24, 34, 0.7)",
    "tab_active_bg": "rgba(94, 169, 255, 0.12)",
    "alert_bg": "rgba(17, 24, 39, 0.6)",
    "chart_bg": "#0b1725",
    "chart_text": "#e5eefb",
    "chart_tick": "#dfeaf9",
    "chart_annotation": "#f8fbff",
    "grid": "rgba(148,163,184,0.16)",
    "axis_line": "rgba(148,163,184,0.30)",
    # A solid navy-blue "card" tint (matches the metric_bg gradient's second
    # stop -- Plotly's legend.bgcolor can't render a CSS gradient) so the
    # legend reads as a distinct floating chip instead of nearly disappearing
    # into chart_bg (#0b1725), which the previous near-identical rgba did.
    "legend_bg": "rgba(18, 78, 140, 0.55)",
    "legend_border": "rgba(94, 169, 255, 0.35)",
}

_LIGHT_TOKENS = {
    "bg_top": "#eef3fb",
    "bg_mid": "#f6f9fd",
    "bg_bottom": "#ffffff",
    "sidebar_bg": "rgba(255, 255, 255, 0.96)",
    "border": "rgba(15, 23, 42, 0.12)",
    "text": "#101728",
    "muted": "#48536b",
    "accent": "#1d6fd6",
    "input_bg": "rgba(241, 245, 251, 0.95)",
    "input_border": "rgba(15, 23, 42, 0.15)",
    "metric_bg": "linear-gradient(135deg, rgba(219, 234, 254, 0.95), rgba(191, 219, 254, 0.65))",
    "metric_border": "rgba(29, 111, 214, 0.28)",
    "metric_label": "#1d4e89",
    "metric_value": "#0b1725",
    "table_bg": "linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(246, 249, 253, 0.96))",
    "table_border": "rgba(29, 111, 214, 0.22)",
    "expander_bg": "linear-gradient(180deg, rgba(255, 255, 255, 0.97), rgba(241, 245, 251, 0.95))",
    "button_bg": "linear-gradient(135deg, rgba(29,111,214,0.10), rgba(255,255,255,0.9))",
    "button_border": "rgba(29,111,214,0.30)",
    "tab_bg": "rgba(15, 23, 42, 0.04)",
    "tab_active_bg": "rgba(29, 111, 214, 0.10)",
    "alert_bg": "rgba(15, 23, 42, 0.04)",
    "chart_bg": "#ffffff",
    "chart_text": "#101728",
    "chart_tick": "#33415c",
    "chart_annotation": "#0b1725",
    "grid": "rgba(15,23,42,0.08)",
    "axis_line": "rgba(15,23,42,0.22)",
    "legend_bg": "rgba(255,255,255,0.88)",
    "legend_border": "rgba(15,23,42,0.14)",
}


_THEME_STATE_KEY = "dashboard_theme_mode"


def _active_theme_type() -> str:
    """'light' or 'dark', from our own sidebar toggle -- deliberately NOT
    `st.context.theme.type`.

    Streamlit's own docs say that API is unreliable exactly when it would
    matter most here: "the theme type may be incorrect ... when the app is
    first loaded within a session" and "when the user changes the theme in
    the settings menu" (see Streamlit GitHub issue #11920). Relying on it
    meant the dashboard could silently render the wrong theme on first load
    or right after a user switched it. `render_theme_toggle()` gives us a
    single source of truth in `st.session_state` instead: 100% deterministic,
    defaults to "dark" (the dashboard's original look) so nothing changes for
    anyone who doesn't touch the toggle, and takes effect the moment it's
    changed since it's rendered before `apply_dashboard_theme()` runs.
    """
    return st.session_state.get(_THEME_STATE_KEY, "dark")


def render_theme_toggle() -> str:
    """Render the sidebar dark/light control and return the active mode.

    Must run before `apply_dashboard_theme()` in `app.main()` so the CSS for
    this very rerun already reflects a just-changed choice, instead of
    lagging one rerun behind like a widget defined later in the script would.
    """
    st.session_state.setdefault(_THEME_STATE_KEY, "dark")
    with st.sidebar:
        st.radio(
            "Tema",
            options=["dark", "light"],
            format_func=lambda v: "🌙 Escuro" if v == "dark" else "☀️ Claro",
            key=_THEME_STATE_KEY,
            horizontal=True,
            label_visibility="collapsed",
        )
    return st.session_state[_THEME_STATE_KEY]


def _tokens() -> dict[str, str]:
    return _LIGHT_TOKENS if _active_theme_type() == "light" else _DARK_TOKENS


def theme_tokens() -> dict[str, str]:
    """Public accessor for the active light/dark token set.

    Use this from a page/component that needs to color its own inline HTML
    or a Plotly Indicator (which `polish_figure_layout` doesn't touch) to
    match the current theme -- see `components.hero_banner` or
    `quality._embedding_readiness` for examples.
    """
    return _tokens()


def apply_dashboard_theme() -> None:
    """Apply an executive-style visual treatment that follows Streamlit's light/dark toggle."""
    t = _tokens()
    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {t["bg_top"]};
            --bg-2: {t["bg_bottom"]};
            --border: {t["border"]};
            --text: {t["text"]};
            --muted: {t["muted"]};
            --accent: {t["accent"]};
        }}

        .stApp {{
            background: linear-gradient(180deg, {t["bg_top"]} 0%, {t["bg_mid"]} 28%, {t["bg_bottom"]} 100%);
            color: var(--text);
        }}

        .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
        }}

        h1, h2, h3, h4, h5, h6,
        p, div, span, label,
        .stCaption, .stMarkdown {{
            color: var(--text) !important;
        }}

        .stMarkdown h1 {{
            font-size: 2.2rem;
            letter-spacing: -0.04em;
            margin-bottom: .25rem;
        }}

        .stMarkdown h2 {{
            font-size: 1.35rem;
            letter-spacing: -0.02em;
            margin-top: 0.25rem;
            margin-bottom: 0.5rem;
        }}

        .stMarkdown p, .stMarkdown li, .stMarkdown div {{
            color: var(--muted) !important;
        }}

        [data-testid="stSidebar"] {{
            background: {t["sidebar_bg"]};
            border-right: 1px solid var(--border);
        }}

        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stMarkdown {{
            color: var(--text) !important;
        }}

        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stMultiSelect,
        [data-testid="stSidebar"] .stSlider,
        [data-testid="stSidebar"] .stNumberInput,
        [data-testid="stSidebar"] .stTextInput,
        [data-testid="stSidebar"] .stDateInput,
        [data-testid="stSidebar"] .stCheckbox,
        [data-testid="stSidebar"] .stRadio,
        [data-testid="stSidebar"] .stButton > button {{
            background: {t["input_bg"]};
            color: var(--text);
            border-color: {t["input_border"]};
        }}

        div[data-baseweb="select"],
        div[data-baseweb="select"] > div,
        div[data-baseweb="popover"] {{
            background: {t["input_bg"]} !important;
            color: var(--text) !important;
            border-color: {t["input_border"]} !important;
        }}

        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div {{
            color: var(--text) !important;
        }}

        .stSlider [data-testid="stThumbValue"],
        .stSlider .stMarkdown p,
        .stSlider label,
        .stSlider span {{
            color: var(--text) !important;
        }}

        .stSlider > div > div > div {{
            background: {t["input_bg"]};
            border: 1px solid {t["input_border"]};
        }}

        [data-testid="stMetric"] {{
            background: {t["metric_bg"]};
            border: 1px solid {t["metric_border"]};
            border-radius: 0.8rem;
            padding: 0.8rem 0.9rem;
            box-shadow: 0 10px 22px rgba(8, 19, 31, 0.18);
        }}

        [data-testid="stMetricLabel"] {{
            font-size: .82rem;
            font-weight: 600;
            color: {t["metric_label"]} !important;
            letter-spacing: .02em;
        }}

        [data-testid="stMetricValue"] {{
            font-size: 1.6rem;
            font-weight: 700;
            color: {t["metric_value"]} !important;
        }}

        div[data-testid="stDataFrame"] {{
            border-radius: 0.6rem;
            border: 1px solid {t["table_border"]};
            overflow: hidden;
            background: {t["table_bg"]};
        }}

        div[data-testid="stExpander"] > details {{
            border: 1px solid {t["table_border"]};
            border-radius: 0.7rem;
            background: {t["expander_bg"]};
        }}

        div[data-testid="stExpander"] summary {{
            color: var(--text) !important;
            font-weight: 600;
        }}

        .stButton > button,
        .stDownloadButton > button {{
            background: {t["button_bg"]};
            color: var(--text);
            border: 1px solid {t["button_border"]};
            border-radius: 0.65rem;
            font-weight: 600;
            transition: all 0.2s ease;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover {{
            border-color: {t["accent"]};
            box-shadow: 0 0 0 1px {t["button_border"]};
            transform: translateY(-1px);
        }}

        .stTabs [role="tablist"] {{
            background: {t["tab_bg"]};
            border: 1px solid var(--border);
            border-radius: 0.7rem;
            padding: 0.1rem;
        }}

        .stTabs [role="tab"] {{
            color: var(--muted) !important;
            border-radius: 0.55rem;
        }}

        .stTabs [role="tab"][aria-selected="true"] {{
            background: {t["tab_active_bg"]};
            color: var(--text) !important;
            border: 1px solid {t["button_border"]};
        }}

        .stTabs [role="tab"]:hover {{
            color: var(--text) !important;
        }}

        .stAlert {{
            background: {t["alert_bg"]};
            border: 1px solid var(--border);
            color: var(--text) !important;
        }}

        .stException {{
            background: rgba(255, 107, 107, 0.12);
            border: 1px solid rgba(255, 107, 107, 0.3);
        }}

        .stPlotlyChart,
        .js-plotly-plot,
        .plot-container {{
            background: {t["chart_bg"]} !important;
        }}

        .js-plotly-plot .svg-container {{
            background: {t["chart_bg"]} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def venue_color_map(venue_rank_list: list[str], others_label: str = "Others") -> dict[str, str]:
    """Assign fixed categorical colors in rank order; the catch-all bucket always gray."""
    colors: dict[str, str] = {}
    slot = 0
    for venue in venue_rank_list:
        if venue == others_label:
            colors[venue] = OTHER_COLOR
        else:
            colors[venue] = CATEGORICAL_PALETTE[slot % len(CATEGORICAL_PALETTE)]
            slot += 1
    return colors


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def polish_figure_layout(fig, height: int | None = None) -> None:
    """Apply unified light/dark styling, with the legend sitting below the title.

    Two things used to be wrong here: with `yanchor="bottom"`, a larger `y`
    means the legend's bottom edge sits higher up, so pushing `y` up to avoid
    a long title actually put the legend *above* the title instead of below
    it. And the "no title" case reused the same tight offset for every
    chart, leaving barely any gap above the plot. `yanchor="top"` makes `y`
    the legend's own top edge (it extends downward from there), so a lower
    `y` than the title's `y` reliably reads as "legend below title" -- and
    both cases now get more breathing room from the top of the canvas.
    """
    t = _tokens()
    has_title = bool(fig.layout.title and fig.layout.title.text)
    top_margin = 105 if has_title else 55
    legend_y = 0.86 if has_title else 1.06

    fig.update_layout(
        margin=dict(l=40, r=40, t=top_margin, b=40),
        font=dict(
            family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            size=12,
            color=t["chart_text"],
        ),
        paper_bgcolor=t["chart_bg"],
        plot_bgcolor=t["chart_bg"],
        xaxis=dict(
            showgrid=True,
            gridcolor=t["grid"],
            zeroline=False,
            linecolor=t["axis_line"],
            tickfont=dict(color=t["chart_tick"]),
            automargin=True,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=t["grid"],
            zeroline=False,
            linecolor=t["axis_line"],
            tickfont=dict(color=t["chart_tick"]),
            automargin=True,
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=legend_y,
            xanchor="left",
            x=0,
            font=dict(color=t["chart_text"]),
            bgcolor=t["legend_bg"],
            bordercolor=t["legend_border"],
        ),
    )
    if has_title:
        fig.update_layout(title=dict(y=0.98, yanchor="top", x=0, xanchor="left"))
    fig.update_xaxes(title_font=dict(color=t["chart_text"]))
    fig.update_yaxes(title_font=dict(color=t["chart_text"]))
    fig.update_annotations(font=dict(weight="bold", color=t["chart_annotation"]))
    try:
        fig.update_traces(textfont=dict(weight="bold", color=t["chart_annotation"]))
    except Exception:
        # Not every trace type accepts a bold textfont weight; this is a
        # cosmetic best-effort, not a correctness concern.
        logger.debug(
            "polish_figure_layout: textfont update unsupported for this trace type", exc_info=True
        )
    if height:
        fig.update_layout(height=height)
