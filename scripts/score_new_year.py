#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Score a new year's Map the Meal Gap data with the persisted 3-year-lag ridge model.

Takes the same kind of raw MMG workbook (ZCTA + County sheets) FTB already downloads each
year, runs it through the same cleaning/feature pipeline used to train the model, and scores
it with the already-fitted weights in models/cc/lag3_ridge.json -- no retraining.

Usage:
    python scripts/score_new_year.py --mmg path/to/MMG_2026_2025-data.xlsx --alice path/to/alice_county.csv

    # Score all states instead of just Florida:
    python scripts/score_new_year.py --mmg new_mmg.xlsx --alice alice_county.csv --state ""

Output: a CSV with one row per ZIP code, showing the driver values used (X) and the
forecasted food insecurity rate (Y) for source_year + 3.
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.data.make_dataset import clean_columns, read_excel_sheet_openpyxl
from src.data.validate import (
    REQUIRED_ALICE_COLUMNS,
    REQUIRED_COUNTY_COLUMNS,
    REQUIRED_ZCTA_COLUMNS,
    ValidationError,
    require_file,
    resolve_source_year,
    validate_columns,
    validate_minimum_coverage,
    validate_workbook_sheets,
)
from src.features.build_features import build_panel
from src.models.predict_model import forecast, load_model

DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "cc" / "lag3_ridge.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "forecasts"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mmg", required=True, type=Path, help="Path to the raw MMG workbook (must have ZCTA and County sheets).")
    parser.add_argument("--alice", required=True, type=Path, help="Path to the Florida ALICE county CSV (from unitedforalice.org). Always required -- there is no default, so scoring never silently falls back to a stale or unexpected file.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help=f"Path to the persisted model JSON. Default: {DEFAULT_MODEL_PATH.relative_to(PROJECT_ROOT)}")
    parser.add_argument("--source-year", type=int, default=None, help="Which year in --mmg to score from, if the file contains more than one year.")
    parser.add_argument("--state", default="FL", help="Two-letter state to restrict output to. Pass an empty string for all states. Default: FL.")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV path. Defaults to forecasts/<state>_food_insecurity_forecast_<year>.csv")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        mmg_path = require_file(args.mmg, "MMG workbook")
        validate_workbook_sheets(mmg_path, ["ZCTA", "County"])

        alice_path = require_file(args.alice, "ALICE CSV")
        print(f"Using ALICE file: {alice_path}")

        print(f"Reading {mmg_path.name} ...")
        zcta_raw = read_excel_sheet_openpyxl(mmg_path, "ZCTA")
        county_raw = read_excel_sheet_openpyxl(mmg_path, "County")
        alice_raw = clean_columns(pd.read_csv(alice_path, dtype=str))

        validate_columns(zcta_raw, REQUIRED_ZCTA_COLUMNS, f"{mmg_path.name} 'ZCTA' sheet")
        validate_columns(county_raw, REQUIRED_COUNTY_COLUMNS, f"{mmg_path.name} 'County' sheet")
        validate_columns(alice_raw, REQUIRED_ALICE_COLUMNS, f"{alice_path.name}")

        source_year = resolve_source_year(zcta_raw, "Year", override=args.source_year)
        print(f"Source year: {source_year}")

        print("Building panel (cleaning, parsing, joining ALICE)...")
        panel = build_panel(zcta_raw, county_raw, alice_raw)

        model = load_model(require_file(args.model, "Model file"))
        driver_cols = model["feature_cols"][1:]

        state = args.state.strip() or None
        n_complete = validate_minimum_coverage(panel, source_year, state, driver_cols)
        print(f"Found {n_complete:,} ZIP rows with complete data at {source_year}" + (f" in {state}" if state else "") + ".")

        forecast_year = source_year + model["rate_lag"]
        print(f"Scoring with {args.model.name} (lag={model['rate_lag']} years) -> forecasting {forecast_year}...")
        result = forecast(model, panel, source_year)
        if state:
            result = result.loc[result["State"].astype(str).str.upper() == state.upper()].copy()
        result = result.sort_values("population", ascending=False).reset_index(drop=True)

    except ValidationError as e:
        print(f"\nInput problem: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        scope = state.lower() if state else "national"
        output_path = DEFAULT_OUTPUT_DIR / f"{scope}_food_insecurity_forecast_{forecast_year}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    scored = result.dropna(subset=["predicted_food_insecurity_rate"])
    n_unscored = len(result) - len(scored)
    mean_rate = (scored["predicted_food_insecurity_rate"] * scored["population"]).sum() / scored["population"].sum()

    print(f"\nWrote {len(result):,} rows to {output_path}")
    if n_unscored:
        print(
            f"Note: {n_unscored} of those rows have a blank prediction -- MMG doesn't publish a "
            f"{source_year} food insecurity estimate for those ZIPs (typically small population), "
            f"so there's no source-year rate for the model to build from. Left in the CSV for "
            f"completeness, just with an empty prediction."
        )
    print(f"Population-weighted average forecasted food insecurity rate for {forecast_year} (scored rows only): {mean_rate:.1%}")


if __name__ == "__main__":
    main()
