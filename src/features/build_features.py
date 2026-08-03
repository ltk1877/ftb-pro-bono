# -*- coding: utf-8 -*-
"""Feature engineering for the ZIP-county-year food insecurity panel.

Shared by notebooks 1.4/1.5/1.6 and by src/models/*, so the panel used to train a model
and the panel used to score new data are always built the exact same way.
"""
import numpy as np
import pandas as pd

# Same 18 drivers used since notebook 1.3, minus the lagged rate itself (added per lag spec).
DRIVER_COLS = [
    "unemployment_rate", "poverty_rate", "percent_black", "percent_hispanic",
    "log_median_income", "homeownership_rate", "disability_rate",
    "county_child_population_share", "county_percent_white_non_hispanic", "county_cost_per_meal",
    "county_weighted_food_cost_index", "county_snap_threshold", "county_rural_urban_code_2023",
    "alice_financial_insecurity_rate", "alice_poverty_household_rate", "alice_threshold_under_65",
    "alice_threshold_65_plus", "has_alice_data",
]

# (driver_lag, rate_lag): how many years back the drivers / lagged rate are measured from the target year.
LAG_SPECS = {
    "current (X[t], rate[t-1])": (0, 1),
    "2-year lag (X[t-2], rate[t-2])": (2, 2),
    "3-year lag (X[t-3], rate[t-3])": (3, 3),
}


def parse_number(series: pd.Series) -> pd.Series:
    """Convert currency, comma-formatted, and percent-looking strings to numeric values."""
    cleaned = (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def parse_rate(series: pd.Series) -> pd.Series:
    """Convert rate columns to decimals, e.g. 15.2% or 15.2 becomes 0.152."""
    values = parse_number(series)
    if values.dropna().max() > 1.5:
        values = values / 100.0
    return values


def clip_rate(series: pd.Series, low: float = 0.0, high: float = 0.95) -> pd.Series:
    """Keep modeled rates inside a plausible bounded interval."""
    return series.clip(lower=low, upper=high)


def build_panel(zcta_raw: pd.DataFrame, county_raw: pd.DataFrame, alice_county_raw: pd.DataFrame) -> pd.DataFrame:
    """Build the ZIP-county-year panel from raw MMG ZCTA/County sheets and Florida ALICE data.

    `state_fips` is derived from `county_fips`'s first two digits rather than a `State FIPS`
    column, since not every MMG release includes that column on the ZCTA sheet.
    """
    zcta = zcta_raw.copy()
    county = county_raw.copy()
    alice_county = alice_county_raw.copy()

    # -----------------------------
    # County-level feature table
    # -----------------------------
    county["county_fips"] = county["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    county["year"] = pd.to_numeric(county["Year"], errors="coerce").astype("Int64")
    county["county_population"] = parse_number(county["Total Population (5 Year ACS)"])
    county["county_child_population"] = parse_number(county["Total Child Population (5 Year ACS)"])
    county["county_child_population_share"] = county["county_child_population"] / county["county_population"]
    county["county_percent_white_non_hispanic"] = parse_rate(county["Percent White, non-Hispanic (5 Year ACS)"])
    county["county_cost_per_meal"] = parse_number(county["Cost Per Meal"])
    county["county_weighted_food_cost_index"] = parse_number(county["Weighted Index"])
    county["county_snap_threshold"] = parse_number(county["SNAP Threshold"])
    county["county_rural_urban_code_2023"] = parse_number(county["Rural-Urban Continuum Code (2023)"])

    county_features = county[[
        "county_fips", "year", "county_child_population_share", "county_percent_white_non_hispanic",
        "county_cost_per_meal", "county_weighted_food_cost_index", "county_snap_threshold",
        "county_rural_urban_code_2023"
    ]].dropna(subset=["county_fips", "year"]).copy()
    county_features["year"] = county_features["year"].astype(int)
    # Two source files should never share a county-year; drop-duplicates is a safety net, not the primary guard.
    county_features = county_features.drop_duplicates(subset=["county_fips", "year"])

    # -----------------------------
    # Florida ALICE county features
    # -----------------------------
    alice_county["year"] = pd.to_numeric(alice_county["Year"], errors="coerce").astype("Int64")
    alice_county["county_fips"] = alice_county["GEO id2"].astype(str).str.zfill(5)
    alice_county["alice_households"] = parse_number(alice_county["ALICE Households"])
    alice_county["alice_poverty_households"] = parse_number(alice_county["Poverty Households"])
    alice_county["alice_total_households"] = parse_number(alice_county["Households"])
    alice_county["alice_financial_insecurity_rate"] = (
        alice_county["alice_households"] + alice_county["alice_poverty_households"]
    ) / alice_county["alice_total_households"]
    alice_county["alice_poverty_household_rate"] = alice_county["alice_poverty_households"] / alice_county["alice_total_households"]
    alice_county["alice_threshold_under_65"] = parse_number(alice_county["ALICE Threshold - HH under 65"])
    alice_county["alice_threshold_65_plus"] = parse_number(alice_county["ALICE Threshold - HH 65 years and over"])

    alice_features = alice_county[[
        "county_fips", "year", "alice_financial_insecurity_rate", "alice_poverty_household_rate",
        "alice_threshold_under_65", "alice_threshold_65_plus"
    ]].dropna(subset=["county_fips", "year"]).copy()
    alice_features["year"] = alice_features["year"].astype(int)

    # -----------------------------
    # ZCTA panel table
    # -----------------------------
    zcta["year"] = pd.to_numeric(zcta["Year"], errors="coerce").astype("Int64")
    zcta["county_fips"] = zcta["County FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    zcta["state_fips"] = zcta["county_fips"].str[:2]
    zcta["zcta"] = zcta["ZCTA"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    zcta["row_id"] = zcta["state_fips"] + "_" + zcta["county_fips"] + "_" + zcta["zcta"]

    zcta["population"] = parse_number(zcta["Total Population (5 Year ACS)"])
    zcta["food_insecurity_rate"] = parse_rate(zcta["Overall Food Insecurity Rate"])
    zcta["food_insecure_persons"] = parse_number(zcta["# of Food Insecure Persons Overall"])
    zcta["unemployment_rate"] = parse_rate(zcta["Unemployment Rate (1 Yr BLS)"])
    zcta["poverty_rate"] = parse_rate(zcta["Poverty Rate (5 Yr ACS)"])
    zcta["percent_black"] = parse_rate(zcta["Percent Black (5 Yr ACS)"])
    zcta["percent_hispanic"] = parse_rate(zcta["Percent Hispanic (any race) (5 Year ACS)"])
    zcta["median_income"] = parse_number(zcta["Median Income (5 Yr ACS)"])
    zcta["log_median_income"] = np.log(zcta["median_income"].replace(0, np.nan))
    zcta["homeownership_rate"] = parse_rate(zcta["Homeownership Rate (5 Yr ACS)"])
    zcta["disability_rate"] = parse_rate(zcta["Disability Rate (5 Yr ACS)"])

    model_cols = [
        "row_id", "state_fips", "county_fips", "zcta", "Geography", "County, State", "State",
        "Food Bank 1 ID", "Food Bank 1", "Food Bank 2 ID", "Food Bank 2", "year", "population",
        "food_insecurity_rate", "food_insecure_persons", "unemployment_rate", "poverty_rate",
        "percent_black", "percent_hispanic", "median_income", "log_median_income",
        "homeownership_rate", "disability_rate"
    ]
    panel = zcta[model_cols].dropna(subset=["year", "row_id"]).copy()
    panel["year"] = panel["year"].astype(int)
    panel = panel.drop_duplicates(subset=["row_id", "year"])

    panel = panel.merge(county_features, on=["county_fips", "year"], how="left")
    panel = panel.merge(alice_features, on=["county_fips", "year"], how="left")
    panel["has_alice_data"] = panel["alice_financial_insecurity_rate"].notna().astype(int)
    panel = panel.sort_values(["row_id", "year"]).reset_index(drop=True)

    # Fill driver gaps with state medians first, then national medians as a final fallback.
    numeric_features = [
        "unemployment_rate", "poverty_rate", "percent_black", "percent_hispanic", "log_median_income",
        "homeownership_rate", "disability_rate", "county_child_population_share",
        "county_percent_white_non_hispanic", "county_cost_per_meal", "county_weighted_food_cost_index",
        "county_snap_threshold", "county_rural_urban_code_2023", "alice_financial_insecurity_rate",
        "alice_poverty_household_rate", "alice_threshold_under_65", "alice_threshold_65_plus", "has_alice_data"
    ]
    for col in numeric_features:
        panel[col] = panel.groupby("State")[col].transform(lambda s: s.fillna(s.median()))
        panel[col] = panel[col].fillna(panel[col].median())

    return panel


def build_transition_table(panel: pd.DataFrame, driver_lag: int, rate_lag: int, driver_cols: list = DRIVER_COLS) -> pd.DataFrame:
    """Pair each row's current-year target with drivers/rate measured `driver_lag`/`rate_lag` years earlier."""
    df = panel.sort_values(["row_id", "year"]).copy()
    g = df.groupby("row_id")

    out = df[["row_id", "year", "population", "food_insecurity_rate", "Food Bank 1", "State"]].copy()
    out["lag_food_insecurity_rate"] = g["food_insecurity_rate"].shift(rate_lag)
    for col in driver_cols:
        out[col] = g[col].shift(driver_lag)
    return out


def build_forecast_inputs(panel: pd.DataFrame, source_year: int, driver_cols: list = DRIVER_COLS) -> pd.DataFrame:
    """Build model inputs for a target year that may not exist in the panel yet.

    Unlike `build_transition_table` (which needs both the source and target year already
    present, for evaluating against a known outcome), this just takes one observed year's
    rate/drivers as-is -- exactly what's available when scoring a real future forecast.
    """
    source = panel.loc[panel["year"] == source_year, ["row_id", "population", "food_insecurity_rate", "Food Bank 1", "State"] + driver_cols].copy()
    return source.rename(columns={"food_insecurity_rate": "lag_food_insecurity_rate"})
