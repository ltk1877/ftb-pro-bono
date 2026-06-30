# Enhanced Annual ZIP-Level Food Insecurity Forecast Methodology

## Purpose

This document describes the methodology used in
`notebooks/1.3-lk-zipcode-food-insecurity-forecast-enhanced-variables.ipynb` to
predict annual food insecurity rates for Feeding Tampa Bay ZIP/ZCTA-county rows
from 2024 through 2031.

This notebook builds on the Map the Meal Gap ZCTA panel model and adds important
county-level and local hardship variables that were available in
`data/external`.

## Source Data

The notebook uses three source tables:

- `data/external/MMG_2025.xlsx`, `ZCTA` sheet
- `data/external/MMG_2025.xlsx`, `County` sheet
- `data/external/2025 ALICE - Florida Data Sheet (Lee).xlsx - County.csv`

The `ZCTA` sheet provides the ZIP/ZCTA panel, including observed food insecurity
rates and ZIP-level economic and demographic drivers for 2020 through 2023.

The `County` sheet provides additional county-level context from Map the Meal
Gap, including food cost and demographic variables. The County sheet does not
include an explicit `Year` column in the file, so the notebook assigns years by
the observed row order within each county: 2019, 2020, 2021, 2022, and 2023.
Those county-year rows are then joined to the ZCTA panel by `county_fips` and
`year`.

The ALICE county file provides Florida county household hardship measures and
ALICE thresholds. Because ALICE is available only for Florida counties in the
current file, the notebook includes a `has_alice_data` flag and fills missing
national ALICE values with medians for model training.

## Forecast Unit

The forecast unit is a ZIP/ZCTA-county row, not a unique ZIP code alone.

The notebook creates:

```text
row_id = State FIPS + County FIPS + ZCTA
```

This is intentional because some ZCTAs cross county boundaries and appear more
than once in the Map the Meal Gap workbook.

With the current Feeding Tampa Bay filter, the forecast includes:

```text
259 ZIP-county rows
241 unique ZCTAs
8 forecast years
2,072 output rows
```

## Target Area

The default target area is set by:

```text
TARGET_FOOD_BANK = "Feeding Tampa Bay"
```

The notebook forecasts latest-year rows where `Food Bank 1` contains `Feeding
Tampa Bay`. Setting `TARGET_FOOD_BANK` to `None` would forecast all latest-year
ZCTA rows instead.

## Observed and Forecast Years

The observed ZCTA panel contains:

```text
2020, 2021, 2022, 2023
```

The latest observed year is 2023. The notebook forecasts:

```text
2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031
```

## Model Type

The notebook uses a population-weighted ridge regression transition model.

The model predicts a ZIP-county row's current-year food insecurity rate using
its prior-year food insecurity rate and current-year driver variables.

Conceptually:

```text
food_insecurity_rate[t] =
    f(food_insecurity_rate[t-1], current economic drivers,
      current demographic drivers, county food-cost context,
      county hardship context)
```

Rows are weighted by population so that very small ZIP-county rows do not
dominate the model fit.

Ridge regression is used because it is stable with correlated predictors and
provides a transparent coefficient table. The notebook implements the weighted
ridge fit directly with NumPy rather than relying on an external machine
learning package.

## Predictors

The model uses the following predictors.

ZIP/ZCTA-level predictors:

- prior-year food insecurity rate
- unemployment rate
- poverty rate
- percent Black
- percent Hispanic
- log median income
- homeownership rate
- disability rate

Added county-level Map the Meal Gap predictors:

- county child population share
- county white non-Hispanic share
- county cost per meal
- county weighted food cost index
- county SNAP threshold
- county 2023 Rural-Urban Continuum Code

Added ALICE county hardship predictors:

- ALICE financial insecurity rate
- ALICE poverty household rate
- ALICE threshold for households under age 65
- ALICE threshold for households age 65 and over
- ALICE data availability flag

The notebook intentionally excludes variables that directly restate the target
or are derived from food insecurity outcomes, such as:

- number of food insecure persons
- meal gap
- county food insecurity rate
- child food insecurity rate
- food insecurity subgroup rates

This avoids target leakage.

## Data Preparation

The notebook normalizes column names, parses numeric fields, and converts rates
to decimals. Median income is transformed with:

```text
log_median_income = log(median_income)
```

Missing feature values are filled in two passes:

1. Use state-level medians when available.
2. Use national medians when state-level values are still missing.

The main model training rows require:

- observed current-year food insecurity rate
- observed prior-year food insecurity rate
- non-missing population

The current training set contains 109,633 ZIP-county-year transition rows.

## Baseline Year Handling

The forecast starts from 2023, the latest observed year.

For each Feeding Tampa Bay row, the notebook preserves:

```text
food_insecurity_rate_2023_observed
```

If a row is missing a 2023 food insecurity rate, the notebook fills the baseline
with a separate same-year ridge model. The baseline source is recorded in:

```text
food_insecurity_baseline_source
```

Current labels are:

- `mmg_zcta_2023_observed`
- `modeled_2023_fallback`

## Local Validation

The notebook includes a local validation section focused on Feeding Tampa Bay
rows.

The validation process is:

1. Train a temporary model using only pre-2023 transition rows.
2. Predict 2023 food insecurity rates.
3. Compare predicted 2023 rates with observed 2023 rates.
4. Report national and Feeding Tampa Bay validation metrics.

Metrics include:

- population-weighted MAE
- population-weighted RMSE
- population-weighted mean error
- population-weighted actual rate
- population-weighted predicted rate

For the current run, Feeding Tampa Bay latest-year holdout validation reported:

```text
Rows: 234
Unique ZCTAs: 216
Population-weighted MAE: 0.0226
Population-weighted RMSE: 0.0235
Population-weighted actual rate: 0.1492
Population-weighted predicted rate: 0.1266
```

The model underpredicted the Feeding Tampa Bay 2023 holdout rate by about 2.26
percentage points on a population-weighted basis. This is important context when
interpreting the forecast.

## Future Driver Estimates

Future predictor values are estimated from the observed 2020-2023 panel with
simple per-row linear trends.

Projected drivers include:

- population
- unemployment rate
- poverty rate
- percent Black
- percent Hispanic
- log median income
- homeownership rate
- disability rate
- county child population share
- county white non-Hispanic share
- county cost per meal
- county weighted food cost index
- ALICE financial insecurity rate
- ALICE poverty household rate
- ALICE thresholds

Because 2020-2023 is a short and unusual period, the notebook caps annual
movements in future driver values. These caps prevent short-run changes from
being extrapolated too aggressively through 2031.

Examples of annual caps:

- unemployment rate: 1 percentage point per year
- poverty rate: 1 percentage point per year
- demographic shares: 1 percentage point per year
- log median income: 4.5 percent per year
- county cost per meal: $0.25 per year
- ALICE financial insecurity rate: 1.5 percentage points per year
- population: plus or minus 3 percent per year around the 2023 baseline

Policy or typology fields are held constant from 2023:

- county SNAP threshold
- county Rural-Urban Continuum Code
- ALICE data availability flag

Rate-like predictors are clipped to valid ranges before forecasting.

## Recursive Forecasting

The model forecasts recursively.

For 2024:

```text
lag_food_insecurity_rate = food_insecurity_rate_2023_used
```

For 2025 through 2031:

```text
lag_food_insecurity_rate[year] =
    predicted_food_insecurity_rate[year - 1]
```

The trained transition model is applied year by year using the projected driver
values for each forecast year.

Predicted rates are clipped between 0 and 0.95:

```text
predicted_food_insecurity_rate =
    min(max(model_prediction, 0), 0.95)
```

Predicted food insecure persons are calculated as:

```text
predicted_food_insecure_persons =
    predicted_food_insecurity_rate * projected_population
```

## Uncertainty Bands

The notebook creates simple residual-based uncertainty bands:

```text
uncertainty_band_low =
    predicted_food_insecurity_rate - 1.64 * residual_standard_deviation

uncertainty_band_high =
    predicted_food_insecurity_rate + 1.64 * residual_standard_deviation
```

These bands are useful diagnostics, but they are not formal prediction
intervals. They do not fully capture uncertainty from future economic conditions,
driver projections, recursive compounding, or model specification.

## Output

The notebook writes:

```text
data/processed/zipcode_food_insecurity_forecast_enhanced_2024_2031.csv
```

Important output fields include:

- `row_id`
- `state_fips`
- `county_fips`
- `zcta`
- `County, State`
- `Food Bank 1`
- `year`
- `food_insecurity_rate_2023_observed`
- `food_insecurity_rate_2023_used`
- `food_insecurity_baseline_source`
- `lag_food_insecurity_rate`
- `predicted_food_insecurity_rate`
- `predicted_food_insecurity_percent`
- `predicted_food_insecure_persons`
- `uncertainty_band_low`
- `uncertainty_band_high`
- `population`
- `unemployment_rate`
- `poverty_rate`
- `percent_black`
- `percent_hispanic`
- `median_income`
- `homeownership_rate`
- `disability_rate`
- `county_child_population_share`
- `county_percent_white_non_hispanic`
- `county_cost_per_meal`
- `county_weighted_food_cost_index`
- `county_snap_threshold`
- `county_rural_urban_code_2023`
- `alice_financial_insecurity_rate`
- `alice_poverty_household_rate`
- `alice_threshold_under_65`
- `alice_threshold_65_plus`
- `has_alice_data`

## Current Forecast Summary

For the current run, the notebook produced the following population-weighted
average Feeding Tampa Bay food insecurity rates:

| Year | Population-weighted predicted rate |
| --- | ---: |
| 2024 | 0.1651 |
| 2025 | 0.1879 |
| 2026 | 0.2168 |
| 2027 | 0.2508 |
| 2028 | 0.2889 |
| 2029 | 0.3306 |
| 2030 | 0.3751 |
| 2031 | 0.4220 |

These rates should be interpreted as a model-driven baseline scenario, not as
official estimates.

## Key Assumptions

The methodology assumes:

- National ZCTA transition patterns are useful for learning ZIP-level food
  insecurity dynamics.
- Feeding Tampa Bay rows follow broadly similar relationships between food
  insecurity and the included economic, demographic, food-cost, and hardship
  predictors.
- The 2023 Map the Meal Gap ZCTA data are the best available baseline.
- Short observed trends from 2020-2023 are a reasonable starting point for
  projecting future drivers when external forecasts are unavailable.
- Annual movement caps make those simple projections more stable over an
  eight-year horizon.
- ZIP-county rows are the correct unit when ZCTAs cross county boundaries.

## Limitations

Important limitations include:

- No observed post-2023 food insecurity rates are used.
- Future drivers are internally extrapolated, not sourced from independent
  economic or demographic forecasts.
- The model is predictive, not causal.
- Forecast error compounds because predictions are recursive.
- The validation section shows local underprediction for the 2023 Feeding Tampa
  Bay holdout.
- ALICE variables are available only for Florida counties in the current file,
  so national training rows rely on median-filled ALICE values plus the
  `has_alice_data` flag.
- Very small ZIP-county rows can produce unstable rates or counts.
- The uncertainty bands are diagnostic and should not be treated as formal
  statistical prediction intervals.

## Recommended Future Improvements

Recommended next improvements are:

1. Replace internal linear driver projections with external forecasts for
   unemployment, poverty, income, population, food cost, and household hardship.
2. Add scenario forecasts, such as baseline, optimistic, and pessimistic driver
   paths.
3. Calibrate ZIP-county forecasts so they aggregate to independently projected
   county totals.
4. Revalidate the model when future Map the Meal Gap releases provide observed
   2024 or later ZCTA food insecurity rates.
5. Consider a local calibration layer for Feeding Tampa Bay rows if future
   validation continues to show systematic underprediction.
6. Compare ridge regression with other transparent panel models before adopting
   a more complex model.
