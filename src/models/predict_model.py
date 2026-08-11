# -*- coding: utf-8 -*-
"""Load a persisted model (from src/models/train_model.save_model) and score new data with it.

This is the "plug and play" half of the pipeline: once a model has been fit and saved, scoring
a new year's data doesn't require re-running any notebook -- just this module plus
src/features/build_features.build_panel to turn new raw MMG/ALICE files into the same
engineered columns the model was trained on.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.build_features import build_forecast_inputs
from src.models.train_model import clip_rate, predict_weighted_ridge


def load_model(path: Path) -> dict:
    """Load a model JSON artifact back into the dict shape `predict_weighted_ridge` expects."""
    with open(path) as f:
        payload = json.load(f)
    return {
        **payload,
        "means": pd.Series(payload["means"], index=payload["features"]),
        "stds": pd.Series(payload["stds"], index=payload["features"]),
        "coef": np.asarray(payload["coef"]),
    }


def forecast(model: dict, panel: pd.DataFrame, source_year: int) -> pd.DataFrame:
    """Forecast `source_year + model['rate_lag']` for every ZIP using data already observed as of `source_year`.

    e.g. a 3-year-lag model with source_year=2025 forecasts 2028, using only 2025 drivers and
    the 2025 rate -- exactly the situation of having data that already lags a few years behind
    the year you actually want a forecast for.
    """
    inputs = build_forecast_inputs(panel, source_year, driver_cols=model["feature_cols"][1:])
    inputs["prediction"] = clip_rate(predict_weighted_ridge(model, inputs[model["feature_cols"]]))
    inputs["forecast_year"] = source_year + model["rate_lag"]
    return inputs[["row_id", "State", "Food Bank 1", "population", "forecast_year", "prediction"]]
