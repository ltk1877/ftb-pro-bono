# -*- coding: utf-8 -*-
"""Fit and evaluate population-weighted linear models for one lag specification.

Supports two variants of the same underlying model:
- `standardize=True` (the default used in notebooks 1.4/1.5): features are rescaled to
  mean 0 / std 1 before a ridge penalty is applied. Coefficients are only interpretable
  in "per standard deviation" terms, but the ridge penalty treats every driver fairly
  regardless of its native units.
- `standardize=False`: plain population-weighted OLS (alpha fixed at 0) on raw-unit
  features. Coefficients are directly interpretable ("per 1-unit change in this driver"),
  at the cost of losing ridge's protection against collinear/noisy drivers.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.build_features import DRIVER_COLS, build_transition_table, clip_rate


def fit_weighted_ridge(X: pd.DataFrame, y: pd.Series, weights: pd.Series, alpha: float = 1.0, standardize: bool = True) -> dict:
    """Fit a population-weighted (ridge, if alpha > 0) linear regression using only NumPy."""
    if standardize:
        means = X.mean()
        stds = X.std(ddof=0).replace(0, 1)
    else:
        # Skip rescaling entirely so coefficients stay in the features' native units.
        means = pd.Series(0.0, index=X.columns)
        stds = pd.Series(1.0, index=X.columns)
    X_scaled = (X - means) / stds

    # Add an intercept column and apply square-root weights for weighted least squares.
    X_design = np.column_stack([np.ones(len(X_scaled)), X_scaled.to_numpy(dtype=float)])
    y_values = y.to_numpy(dtype=float)
    w = np.sqrt(np.maximum(weights.fillna(weights.median()).to_numpy(dtype=float), 1.0))
    Xw = X_design * w[:, None]
    yw = y_values * w

    # Penalize feature coefficients but not the intercept. alpha=0 reduces this to plain OLS.
    penalty = np.eye(X_design.shape[1]) * alpha
    penalty[0, 0] = 0
    try:
        coef = np.linalg.solve(Xw.T @ Xw + penalty, Xw.T @ yw)
    except np.linalg.LinAlgError:
        # Raw-unit design matrices can be closer to singular than standardized ones; fall back
        # to a least-squares solve rather than failing outright.
        coef, *_ = np.linalg.lstsq(Xw.T @ Xw + penalty, Xw.T @ yw, rcond=None)
    return {"features": list(X.columns), "means": means, "stds": stds, "coef": coef, "standardize": standardize}


def predict_weighted_ridge(model: dict, X: pd.DataFrame) -> pd.Series:
    """Generate predictions from a fitted weighted linear model (ridge or OLS)."""
    means = pd.Series(model["means"], index=model["features"]) if not isinstance(model["means"], pd.Series) else model["means"]
    stds = pd.Series(model["stds"], index=model["features"]) if not isinstance(model["stds"], pd.Series) else model["stds"]
    X_scaled = (X[model["features"]] - means) / stds
    X_design = np.column_stack([np.ones(len(X_scaled)), X_scaled.to_numpy(dtype=float)])
    coef = np.asarray(model["coef"])
    return pd.Series(X_design @ coef, index=X.index)


def weighted_metrics(frame: pd.DataFrame, actual_col: str, pred_col: str, weight_col: str = "population") -> dict:
    """Population-weighted MAE / RMSE / mean error."""
    if frame.empty:
        return {"weighted_mae": np.nan, "weighted_rmse": np.nan, "weighted_mean_error": np.nan, "n": 0}
    w = frame[weight_col].fillna(1).clip(lower=1)
    err = frame[pred_col] - frame[actual_col]
    return {
        "weighted_mae": float(np.average(err.abs(), weights=w)),
        "weighted_rmse": float(np.sqrt(np.average(err ** 2, weights=w))),
        "weighted_mean_error": float(np.average(err, weights=w)),
        "n": int(len(frame)),
    }


def evaluate_lag_spec(
    panel: pd.DataFrame,
    label: str,
    driver_lag: int,
    rate_lag: int,
    driver_cols: list = DRIVER_COLS,
    target_state: str = "FL",
    target_food_bank: str = "Feeding Tampa Bay",
    standardize: bool = True,
    alpha_grid=(0.01, 0.1, 0.5, 1.0, 2.0),
    n_folds: int = 5,
    random_state: int = 42,
) -> dict:
    """Fit a population-weighted linear model on the full national panel for one lag specification.

    Trains on all states but reports metrics nationally, for Florida overall, and for the
    Feeding Tampa Bay slice specifically. Uses a time-based holdout (train on earlier
    transition years, evaluate on the latest available one) whenever at least two transition
    years exist for this lag; falls back to 5-fold cross-validation across ZIP-county rows
    when the lag leaves only one usable transition year.

    When `standardize=False`, alpha is fixed at 0 (plain OLS) rather than grid-searched --
    there is no ridge penalty to tune.
    """
    feature_cols = ["lag_food_insecurity_rate"] + driver_cols
    table = build_transition_table(panel, driver_lag, rate_lag, driver_cols)
    valid = table.dropna(subset=["food_insecurity_rate", "lag_food_insecurity_rate", "population"] + driver_cols).copy()

    valid["is_fl"] = valid["State"].astype(str).str.upper() == target_state.upper() if target_state else True
    valid["is_ftb"] = (
        valid["Food Bank 1"].astype(str).str.contains(target_food_bank, case=False, na=False)
        if target_food_bank else True
    )

    available_years = sorted(valid["year"].unique().tolist())
    if len(available_years) == 0:
        raise ValueError(f"{label}: no usable transitions for driver_lag={driver_lag}, rate_lag={rate_lag}.")

    search_alphas = (0.0,) if not standardize else alpha_grid

    def score(train_df, test_df, alpha):
        m = fit_weighted_ridge(train_df[feature_cols], train_df["food_insecurity_rate"], train_df["population"], alpha=alpha, standardize=standardize)
        pred = clip_rate(predict_weighted_ridge(m, test_df[feature_cols]))
        return test_df.assign(prediction=pred), m

    if len(available_years) >= 2:
        method = "time_holdout"
        latest_year = available_years[-1]
        train_full = valid.loc[valid["year"] < latest_year].copy()
        test = valid.loc[valid["year"] == latest_year].copy()

        alpha_rows = []
        for alpha in search_alphas:
            scored, _ = score(train_full, test, alpha)
            fl = weighted_metrics(scored.loc[scored["is_fl"]], "food_insecurity_rate", "prediction")
            nat = weighted_metrics(scored, "food_insecurity_rate", "prediction")
            alpha_rows.append({"alpha": alpha, "fl_weighted_mae": fl["weighted_mae"], "national_weighted_mae": nat["weighted_mae"]})
        alpha_df = pd.DataFrame(alpha_rows)
        selection_metric = "fl_weighted_mae" if alpha_df["fl_weighted_mae"].notna().any() else "national_weighted_mae"
        selected_alpha = float(alpha_df.sort_values([selection_metric, "national_weighted_mae", "alpha"]).iloc[0]["alpha"])

        scored, final_model = score(train_full, test, selected_alpha)
        train_years = sorted(train_full["year"].unique().tolist())
        n_train = len(train_full)
        n_test = len(test)

    else:
        method = "5_fold_cv_fallback"
        shuffled = valid.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
        shuffled["fold"] = np.arange(len(shuffled)) % n_folds

        def run_cv(alpha):
            fold_frames = []
            for f in range(n_folds):
                train_fold = shuffled.loc[shuffled["fold"] != f]
                test_fold = shuffled.loc[shuffled["fold"] == f]
                scored_fold, _ = score(train_fold, test_fold, alpha)
                fold_frames.append(scored_fold)
            return pd.concat(fold_frames, ignore_index=True)

        alpha_rows = []
        for alpha in search_alphas:
            cv_scored = run_cv(alpha)
            fl = weighted_metrics(cv_scored.loc[cv_scored["is_fl"]], "food_insecurity_rate", "prediction")
            nat = weighted_metrics(cv_scored, "food_insecurity_rate", "prediction")
            alpha_rows.append({"alpha": alpha, "fl_weighted_mae": fl["weighted_mae"], "national_weighted_mae": nat["weighted_mae"]})
        alpha_df = pd.DataFrame(alpha_rows)
        selection_metric = "fl_weighted_mae" if alpha_df["fl_weighted_mae"].notna().any() else "national_weighted_mae"
        selected_alpha = float(alpha_df.sort_values([selection_metric, "national_weighted_mae", "alpha"]).iloc[0]["alpha"])

        scored = run_cv(selected_alpha)
        final_model = fit_weighted_ridge(shuffled[feature_cols], shuffled["food_insecurity_rate"], shuffled["population"], alpha=selected_alpha, standardize=standardize)
        train_years = available_years
        n_train = len(shuffled)
        n_test = len(scored)

    national_metrics = weighted_metrics(scored, "food_insecurity_rate", "prediction")
    fl_metrics = weighted_metrics(scored.loc[scored["is_fl"]], "food_insecurity_rate", "prediction")
    ftb_metrics = weighted_metrics(scored.loc[scored["is_ftb"]], "food_insecurity_rate", "prediction")

    return {
        "label": label,
        "driver_lag": driver_lag,
        "rate_lag": rate_lag,
        "standardize": standardize,
        "validation_method": method,
        "selected_alpha": selected_alpha,
        "available_years": available_years,
        "train_years": train_years,
        "n_train": n_train,
        "n_test": n_test,
        "national_weighted_mae": national_metrics["weighted_mae"],
        "national_weighted_rmse": national_metrics["weighted_rmse"],
        "national_weighted_mean_error": national_metrics["weighted_mean_error"],
        "national_n": national_metrics["n"],
        "fl_weighted_mae": fl_metrics["weighted_mae"],
        "fl_weighted_rmse": fl_metrics["weighted_rmse"],
        "fl_weighted_mean_error": fl_metrics["weighted_mean_error"],
        "fl_n": fl_metrics["n"],
        "ftb_weighted_mae": ftb_metrics["weighted_mae"],
        "ftb_weighted_rmse": ftb_metrics["weighted_rmse"],
        "ftb_weighted_mean_error": ftb_metrics["weighted_mean_error"],
        "ftb_n": ftb_metrics["n"],
        "model": final_model,
        "feature_cols": feature_cols,
    }


def save_model(result: dict, path: Path) -> None:
    """Persist a fitted model plus its evaluation metadata to a JSON file for later scoring."""
    model = result["model"]
    payload = {
        "label": result["label"],
        "driver_lag": result["driver_lag"],
        "rate_lag": result["rate_lag"],
        "standardize": result["standardize"],
        "validation_method": result["validation_method"],
        "selected_alpha": result["selected_alpha"],
        "train_years": result["train_years"],
        "n_train": result["n_train"],
        "n_test": result["n_test"],
        "metrics": {
            "national_weighted_mae": result["national_weighted_mae"],
            "national_weighted_rmse": result["national_weighted_rmse"],
            "fl_weighted_mae": result["fl_weighted_mae"],
            "fl_weighted_rmse": result["fl_weighted_rmse"],
            "ftb_weighted_mae": result["ftb_weighted_mae"],
            "ftb_weighted_rmse": result["ftb_weighted_rmse"],
        },
        "feature_cols": result["feature_cols"],
        "features": model["features"],
        "means": list(np.asarray(model["means"], dtype=float)),
        "stds": list(np.asarray(model["stds"], dtype=float)),
        "coef": list(np.asarray(model["coef"], dtype=float)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
