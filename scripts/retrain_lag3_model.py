#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Refit the persisted 3-year-lag ridge model (models/cc/lag3_ridge.json) on new MMG/ALICE data.

The training-side counterpart to scripts/score_new_year.py. Where that tool scores new data
against already-fitted weights, this tool refits those weights -- population-weighted ridge
regression, standardized features, `driver_lag=3, rate_lag=3` only (no other lag spec or the
raw-unit OLS variant; see notebook 1.6-cc-persisted-ridge-vs-ols-model.ipynb if you need those).
Coefficients reflect only the driver/outcome relationships observed in the data given to this
run, so re-run it whenever a new year of MMG data lands rather than trusting one saved model
indefinitely -- the scoring code in predict_model.py / score_new_year.py stays the same either
way, only the saved coefficients get refreshed.

Usage:
    # Single workbook covering all years:
    python scripts/retrain_lag3_model.py --mmg path/to/MMG_2019-2024.xlsx --alice path/to/alice_county.csv

    # Multiple workbooks (e.g. successive MMG releases) -- pass in chronological order, since
    # rows for the same (county_fips, zcta, year) that appear in more than one file keep the
    # first-seen value:
    python scripts/retrain_lag3_model.py --mmg data/external/MMG_2019-2023.xlsx data/external/MMG_2024.xlsx --alice path/to/alice_county.csv

    # Write somewhere other than the production model path, to inspect before promoting it:
    python scripts/retrain_lag3_model.py --mmg new_mmg.xlsx --alice alice_county.csv --output models/cc/lag3_ridge_candidate.json

By default this OVERWRITES models/cc/lag3_ridge.json, the file scripts/score_new_year.py reads
from by default -- that file is tracked in git, so a bad refit is recoverable from git history.
Every run also appends one row to results/cc/lag3_retrain_history.csv (train years, validation
method, alpha, and weighted MAE/RMSE) so accuracy can be tracked across refits over time.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from src.data.make_dataset import clean_columns, read_sheet_from_workbooks
from src.data.validate import (
    REQUIRED_ALICE_COLUMNS,
    REQUIRED_COUNTY_COLUMNS,
    REQUIRED_ZCTA_COLUMNS,
    ValidationError,
    require_file,
    validate_columns,
    validate_minimum_training_rows,
    validate_workbook_sheets,
)
from src.features.build_features import DRIVER_COLS, build_panel, build_transition_table, clip_rate
from src.models.predict_model import load_model
from src.models.train_model import evaluate_lag_spec, predict_weighted_ridge, save_model

DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "cc" / "lag3_ridge.json"
DEFAULT_RESULTS_LOG = PROJECT_ROOT / "results" / "cc" / "lag3_retrain_history.csv"

LABEL = "3-year lag (X[t-3], rate[t-3])"
DRIVER_LAG = 3
RATE_LAG = 3


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mmg", required=True, nargs="+", type=Path, help="Path(s) to raw MMG workbook(s) (each must have ZCTA and County sheets). Pass in chronological order.")
    parser.add_argument("--alice", required=True, type=Path, help="Path to the Florida ALICE county CSV (from unitedforalice.org). Always required -- there is no default, so a refit never silently pulls in a stale or unexpected file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH, help=f"Where to save the refit model JSON. Default: {DEFAULT_MODEL_PATH.relative_to(PROJECT_ROOT)} (overwrites the production model).")
    parser.add_argument("--results-log", type=Path, default=DEFAULT_RESULTS_LOG, help=f"CSV to append a fit-summary row to. Default: {DEFAULT_RESULTS_LOG.relative_to(PROJECT_ROOT)}")
    parser.add_argument("--state", default="FL", help="Two-letter state used for the FL-specific evaluation slice. Pass an empty string to skip that slice (national only). Default: FL.")
    parser.add_argument("--food-bank", default="Feeding Tampa Bay", help="Food bank name (substring match) used for the FTB-specific evaluation slice. Pass an empty string to skip it. Default: 'Feeding Tampa Bay'.")
    parser.add_argument("--alpha-grid", default=None, help="Comma-separated ridge alphas to search, e.g. '0.01,0.1,0.5,1,2'. Defaults to evaluate_lag_spec's built-in grid.")
    return parser.parse_args()


def main():
    args = parse_args()
    state = args.state.strip() or None
    food_bank = args.food_bank.strip() or None

    try:
        mmg_paths = [require_file(p, "MMG workbook") for p in args.mmg]
        for p in mmg_paths:
            validate_workbook_sheets(p, ["ZCTA", "County"])

        alice_path = require_file(args.alice, "ALICE CSV")
        print(f"Using ALICE file: {alice_path}")

        print(f"Reading {len(mmg_paths)} MMG workbook(s): {', '.join(p.name for p in mmg_paths)} ...")
        zcta_raw = read_sheet_from_workbooks(mmg_paths, "ZCTA")
        county_raw = read_sheet_from_workbooks(mmg_paths, "County")
        alice_raw = clean_columns(pd.read_csv(alice_path, dtype=str))

        validate_columns(zcta_raw, REQUIRED_ZCTA_COLUMNS, "combined MMG 'ZCTA' sheets")
        validate_columns(county_raw, REQUIRED_COUNTY_COLUMNS, "combined MMG 'County' sheets")
        validate_columns(alice_raw, REQUIRED_ALICE_COLUMNS, alice_path.name)

        print("Building panel (cleaning, parsing, joining ALICE)...")
        panel = build_panel(zcta_raw, county_raw, alice_raw)
        observed_years = sorted(panel["year"].dropna().unique().tolist())
        print(f"Observed years: {observed_years} ({len(panel):,} rows, {panel['row_id'].nunique():,} unique ZIPs)")

        validate_minimum_training_rows(panel, DRIVER_LAG, RATE_LAG, DRIVER_COLS)

        print(f"Fitting {LABEL} (ridge, standardized)...")
        alpha_grid = tuple(float(a) for a in args.alpha_grid.split(",")) if args.alpha_grid else None
        fit_kwargs = {"alpha_grid": alpha_grid} if alpha_grid else {}
        result = evaluate_lag_spec(
            panel=panel,
            label=LABEL,
            driver_lag=DRIVER_LAG,
            rate_lag=RATE_LAG,
            driver_cols=DRIVER_COLS,
            target_state=state,
            target_food_bank=food_bank,
            standardize=True,
            **fit_kwargs,
        )

        print(f"Validation method: {result['validation_method']}", end="")
        if result["validation_method"] == "5_fold_cv_fallback":
            print(" (WARNING: too few distinct transition years for a real time-based holdout -- treat metrics as lower-confidence)")
        else:
            print(f" (trained on {result['train_years']}, tested on the latest year)")
        print(f"Selected alpha: {result['selected_alpha']:g}")
        print(f"National weighted MAE: {result['national_weighted_mae']:.4f}  RMSE: {result['national_weighted_rmse']:.4f}")
        if state:
            print(f"{state} weighted MAE: {result['fl_weighted_mae']:.4f}  RMSE: {result['fl_weighted_rmse']:.4f}")
        if food_bank:
            print(f"{food_bank} weighted MAE: {result['ftb_weighted_mae']:.4f}  RMSE: {result['ftb_weighted_rmse']:.4f}")

        save_model(result, args.output)
        print(f"Saved model to {args.output}")

        print("Verifying persistence round-trip...")
        table = build_transition_table(panel, DRIVER_LAG, RATE_LAG, DRIVER_COLS)
        valid = table.dropna(subset=["food_insecurity_rate", "lag_food_insecurity_rate", "population"] + DRIVER_COLS)
        in_memory_pred = clip_rate(predict_weighted_ridge(result["model"], valid[result["feature_cols"]]))
        reloaded_pred = clip_rate(predict_weighted_ridge(load_model(args.output), valid[result["feature_cols"]]))
        if not np.allclose(in_memory_pred.to_numpy(), reloaded_pred.to_numpy(), rtol=1e-6, atol=1e-9):
            print("Persisted model did NOT reproduce the in-memory fit -- refusing to trust this artifact.", file=sys.stderr)
            sys.exit(1)
        print("Match -- the persisted artifact reproduces the original fit.")

    except ValidationError as e:
        print(f"\nInput problem: {e}", file=sys.stderr)
        sys.exit(1)

    history_row = {
        "retrained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mmg_files": ", ".join(p.name for p in mmg_paths),
        "alice_file": alice_path.name,
        "observed_years": str(observed_years),
        "validation_method": result["validation_method"],
        "train_years": str(result["train_years"]),
        "n_train": result["n_train"],
        "n_test": result["n_test"],
        "selected_alpha": result["selected_alpha"],
        "national_weighted_mae": result["national_weighted_mae"],
        "national_weighted_rmse": result["national_weighted_rmse"],
        "fl_weighted_mae": result["fl_weighted_mae"],
        "fl_weighted_rmse": result["fl_weighted_rmse"],
        "ftb_weighted_mae": result["ftb_weighted_mae"],
        "ftb_weighted_rmse": result["ftb_weighted_rmse"],
        "output_model": str(args.output),
    }
    args.results_log.parent.mkdir(parents=True, exist_ok=True)
    write_header = not args.results_log.exists()
    pd.DataFrame([history_row]).to_csv(args.results_log, mode="a", header=write_header, index=False)
    print(f"Logged fit summary to {args.results_log}")

    if args.output == DEFAULT_MODEL_PATH:
        print(f"\nNote: this overwrote the production model at {DEFAULT_MODEL_PATH.relative_to(PROJECT_ROOT)} "
              f"(scripts/score_new_year.py's default). Previous version is recoverable via git history.")


if __name__ == "__main__":
    main()
