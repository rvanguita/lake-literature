"""Publication-volume forecasting: candidate regression models, validated by a
held-out year plus rolling-origin cross-validation, then used to project two
years ahead.

Pure pandas/sklearn -- no `streamlit` import, mirroring `analytics.py` -- so
the modeling logic can be reasoned about (and unit-tested) independently of
the page that renders it.

Why regression instead of a heavier ML model: the usable series is short
(~16 yearly points, 2010-2025 -- the same cutoff `topics.TREND_MIN_YEAR` uses
for keyword trends). A random forest or neural net would overfit a series
this small; three simple regressions plus model selection by validation
error is the appropriate amount of machine learning for the amount of data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures

MIN_TRAIN_YEAR = 2010  # matches topics.TREND_MIN_YEAR -- earlier years are too sparse to trend
TRAIN_END_YEAR = 2025  # last *complete* year in the corpus
HOLDOUT_YEAR = 2026  # current year at collection time -- a partial year, not a complete one
FORECAST_YEARS = (2027, 2028)
CV_YEARS = (2023, 2024, 2025)  # rolling-origin validation over the last complete years

_CANDIDATES = ("linear", "polynomial", "log_linear")


def _fit_model(kind: str, years: np.ndarray, values: np.ndarray):
    x = years.reshape(-1, 1)
    if kind == "linear":
        model = LinearRegression().fit(x, values)
        return lambda yrs: model.predict(np.asarray(yrs).reshape(-1, 1))
    if kind == "polynomial":
        model = make_pipeline(PolynomialFeatures(degree=2), LinearRegression()).fit(x, values)
        return lambda yrs: model.predict(np.asarray(yrs).reshape(-1, 1))
    if kind == "log_linear":
        model = LinearRegression().fit(x, np.log1p(values))
        return lambda yrs: np.expm1(model.predict(np.asarray(yrs).reshape(-1, 1)))
    raise ValueError(f"unknown model kind: {kind}")


def _mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(actual) - np.asarray(predicted))))


@dataclass
class ForecastResult:
    history: pd.Series  # full observed series, MIN_TRAIN_YEAR..(latest available year)
    train_years: np.ndarray
    fitted_curve: pd.Series  # model's fit over the training range, for display
    holdout_year: int
    holdout_actual: float | None
    holdout_predicted: float | None
    cv_mae: float | None  # mean MAE across CV_YEARS rolling-origin folds
    model_comparison: pd.DataFrame  # one row per candidate: holdout MAE, CV MAE
    chosen_model: str
    forecast_years: tuple[int, ...]
    forecast_values: np.ndarray
    forecast_lower: np.ndarray
    forecast_upper: np.ndarray
    r2_train: float
    insufficient_data: bool = False
    notes: list[str] = field(default_factory=list)


def yearly_counts(df: pd.DataFrame, source: str | None = None) -> pd.Series:
    """Article counts per year, optionally restricted to one source.

    Returns a series indexed by int year, covering every year from the
    earliest to the latest observed (gaps filled with 0) so a regression over
    `year` doesn't silently skip missing years.
    """
    working = df.copy()
    if source is not None:
        if "source" in working.columns:
            working = working[working["source"] == source]
        elif "sources" in working.columns:
            working = working[working["sources"].apply(lambda s: isinstance(s, list) and source in s)]
    years = pd.to_numeric(working.get("year"), errors="coerce").dropna().astype(int)
    if years.empty:
        return pd.Series(dtype=float)
    counts = years.value_counts().sort_index()
    full_index = range(int(counts.index.min()), int(counts.index.max()) + 1)
    return counts.reindex(full_index, fill_value=0).astype(float)


def _rolling_origin_cv(years: np.ndarray, values: np.ndarray, cv_years: tuple[int, ...]) -> dict[str, float]:
    """Mean CV MAE per candidate: for each year in `cv_years`, train on every
    earlier year in `years` and score against that year's actual value.
    """
    errors: dict[str, list[float]] = {kind: [] for kind in _CANDIDATES}
    for cv_year in cv_years:
        train_mask = years < cv_year
        if train_mask.sum() < 3 or cv_year not in years:
            continue
        train_x, train_y = years[train_mask], values[train_mask]
        actual = values[years == cv_year][0]
        for kind in _CANDIDATES:
            try:
                predict = _fit_model(kind, train_x, train_y)
                errors[kind].append(_mae([actual], predict([cv_year])))
            except Exception:
                continue
    return {kind: float(np.mean(v)) if v else float("nan") for kind, v in errors.items()}


def fit_and_forecast(
    series: pd.Series,
    *,
    min_train_year: int = MIN_TRAIN_YEAR,
    train_end_year: int = TRAIN_END_YEAR,
    holdout_year: int = HOLDOUT_YEAR,
    forecast_years: tuple[int, ...] = FORECAST_YEARS,
    cv_years: tuple[int, ...] = CV_YEARS,
) -> ForecastResult:
    """Fit 3 candidate regressions, validate, select, and forecast ahead.

    Selection uses the mean of the 2026 holdout MAE and the rolling-origin CV
    MAE (2023-2025) -- relying on the holdout alone would overweight a single,
    partial year. The chosen model is then refit on every real year available
    (through `holdout_year`, inclusive) before projecting `forecast_years`.
    """
    notes: list[str] = []
    history = series[series.index >= min_train_year]
    train = history[history.index <= train_end_year]

    if len(train) < 4:
        empty = np.array([])
        return ForecastResult(
            history=history,
            train_years=empty,
            fitted_curve=pd.Series(dtype=float),
            holdout_year=holdout_year,
            holdout_actual=None,
            holdout_predicted=None,
            cv_mae=None,
            model_comparison=pd.DataFrame(),
            chosen_model="none",
            forecast_years=forecast_years,
            forecast_values=empty,
            forecast_lower=empty,
            forecast_upper=empty,
            r2_train=float("nan"),
            insufficient_data=True,
            notes=["Anos de treino insuficientes (mínimo 4) para ajustar um modelo."],
        )

    train_years = train.index.to_numpy()
    train_values = train.to_numpy()

    holdout_actual = float(history.loc[holdout_year]) if holdout_year in history.index else None

    cv_mae_by_model = _rolling_origin_cv(train_years, train_values, cv_years)

    rows = []
    for kind in _CANDIDATES:
        predict = _fit_model(kind, train_years, train_values)
        holdout_pred = float(predict([holdout_year])[0]) if holdout_actual is not None else float("nan")
        holdout_mae = abs(holdout_pred - holdout_actual) if holdout_actual is not None else float("nan")
        rows.append(
            {
                "model": kind,
                "holdout_mae": holdout_mae,
                "cv_mae": cv_mae_by_model.get(kind, float("nan")),
            }
        )
    comparison = pd.DataFrame(rows)

    # Combined score: mean of whichever validation signals are available.
    def _combined(row) -> float:
        vals = [v for v in (row["holdout_mae"], row["cv_mae"]) if v == v]  # drop NaN
        return float(np.mean(vals)) if vals else float("inf")

    comparison["combined_mae"] = comparison.apply(_combined, axis=1)
    chosen_model = comparison.loc[comparison["combined_mae"].idxmin(), "model"]

    # Refit the chosen model on every real year through the holdout year.
    final_train = history[history.index <= holdout_year]
    final_years = final_train.index.to_numpy()
    final_values = final_train.to_numpy()
    final_predict = _fit_model(chosen_model, final_years, final_values)

    fitted_curve = pd.Series(final_predict(final_years), index=final_years)
    residuals = final_values - fitted_curve.to_numpy()
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 2 else float(np.std(residuals))
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((final_values - final_values.mean()) ** 2))
    r2_train = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    forecast_values = final_predict(np.array(forecast_years))
    forecast_values = np.clip(forecast_values, 0, None)  # counts can't be negative
    margin = 1.96 * residual_std
    forecast_lower = np.clip(forecast_values - margin, 0, None)
    forecast_upper = forecast_values + margin

    # Holdout prediction for the *chosen* model, fit on train-only years (not
    # the final refit, which already includes the holdout year in training).
    holdout_predicted = None
    if holdout_actual is not None:
        train_only_predict = _fit_model(chosen_model, train_years, train_values)
        holdout_predicted = float(train_only_predict([holdout_year])[0])
        notes.append(
            f"O erro contra {holdout_year} compara com um ano ainda em andamento na coleta do corpus "
            "(dado parcial), não um ano completo."
        )
    if (train_values.max() if len(train_values) else 0) < 20:
        notes.append("Série de baixo volume — a banda de confiança é proporcionalmente mais larga.")

    return ForecastResult(
        history=history,
        train_years=train_years,
        fitted_curve=fitted_curve,
        holdout_year=holdout_year,
        holdout_actual=holdout_actual,
        holdout_predicted=holdout_predicted,
        cv_mae=cv_mae_by_model.get(chosen_model),
        model_comparison=comparison,
        chosen_model=chosen_model,
        forecast_years=forecast_years,
        forecast_values=forecast_values,
        forecast_lower=forecast_lower,
        forecast_upper=forecast_upper,
        r2_train=r2_train,
        notes=notes,
    )
