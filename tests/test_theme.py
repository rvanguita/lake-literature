"""Contract for the chart chrome that Streamlit would otherwise fill in itself.

Streamlit's frontend runs `layoutWithThemeDefaults` over every Plotly spec --
including with `theme=None`, which is what `components.render_chart` passes --
and backfills `paper_bgcolor`, `plot_bgcolor` and `font` from *its own* theme
whenever the figure's layout doesn't carry them. It reads the figure, never the
template, so styling declared only in `_figure_template` lost to Streamlit's
near-black background and every chart rendered as a black slab on the
dashboard's navy page. These assert the keys reach the serialized figure, where
Streamlit looks for them.
"""

import pandas as pd
import plotly.express as px
import pytest
import streamlit as st

from lake_literature.dashboard.theme import (
    _DARK_TOKENS,
    _LIGHT_TOKENS,
    _THEME_STATE_KEY,
    CHART_PAPER_BG,
    polish_figure_layout,
)


@pytest.fixture
def theme_mode():
    """Switch the dashboard's dark/light mode for one test, then restore it.

    `st.session_state` works outside `streamlit run` (it only warns), which is
    what lets the theme be exercised without a running app.
    """
    original = st.session_state.get(_THEME_STATE_KEY)

    def _set(mode: str) -> None:
        st.session_state[_THEME_STATE_KEY] = mode

    yield _set

    if original is None:
        del st.session_state[_THEME_STATE_KEY]
    else:
        st.session_state[_THEME_STATE_KEY] = original


def _polished_layout() -> dict:
    fig = px.scatter(pd.DataFrame({"x": [1, 2], "y": [3, 4]}), x="x", y="y")
    polish_figure_layout(fig)
    return fig.to_dict()["layout"]


def test_background_lands_on_the_figure_not_only_the_template(theme_mode) -> None:
    theme_mode("dark")
    layout = _polished_layout()
    # Straight off the figure: `layout["template"]` having the color is exactly
    # the case Streamlit ignores.
    assert layout["paper_bgcolor"] == CHART_PAPER_BG
    assert layout["plot_bgcolor"] == CHART_PAPER_BG


def test_figure_font_follows_the_dashboard_theme(theme_mode) -> None:
    theme_mode("dark")
    assert _polished_layout()["font"]["color"] == _DARK_TOKENS["chart_text"]
    theme_mode("light")
    assert _polished_layout()["font"]["color"] == _LIGHT_TOKENS["chart_text"]


def test_hover_box_keeps_a_solid_themed_fill(theme_mode) -> None:
    # With a transparent canvas, an unnamed hoverlabel background resolves to a
    # transparent box -- unreadable, most visibly on the `hovermode="x unified"`
    # charts.
    theme_mode("light")
    template = _polished_layout()["template"]
    assert template["layout"]["hoverlabel"]["bgcolor"] == _LIGHT_TOKENS["chart_bg"]


def test_both_themes_define_the_same_tokens() -> None:
    # A token added to one dict only is a color that silently comes out wrong
    # in the other theme.
    assert set(_DARK_TOKENS) == set(_LIGHT_TOKENS)
