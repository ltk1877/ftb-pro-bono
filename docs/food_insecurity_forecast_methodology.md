# Annual ZIP-Level Food Insecurity Forecast Methodology

## Purpose

This document describes the updated methodology used in
`notebooks/1.2-lk-zipcode-food-insecurity-forecast-mmg-panel.ipynb` to predict
annual food insecurity rates at the ZIP/ZCTA level for the eight years after the
latest observed year in `data/external/MMG_2025.xlsx`.

The current forecast covers 2024 through 2031. It uses the newly added
`MMG_2025.xlsx` workbook, which includes a multi-year ZCTA panel for 2020
through 2023. This is an improvement over the earlier projection-only approach
because the model can now learn from observed ZIP/ZCTA year-to-year changes.

## Source Data

The primary source is:

`data/external/MMG_2025.xlsx`

The notebook uses the `ZCTA` sheet. Important fields include:

- `State FIPS`
- `County FIPS`
- `ZCTA`
- `Geography`
- `County, State`
- `State`
- `Year`
- `Food Bank 1 ID`
- `Food Bank 1`
- `Food Bank 2 ID`
- `Food Bank 2`
- `Total Population (5 Year ACS)`
- `Overall Food Insecurity Rate`
- `# of Food Insecure Persons Overall`
- `Unemployment Rate (1 Yr BLS)`
- `Poverty Rate (5 Yr ACS)`
- `Percent Black (5 Yr ACS)`
- `Percent Hispanic (any race) (5 Year ACS)`
- `Median Income (5 Yr ACS)`
- `Homeownership Rate (5 Yr ACS)`
- `Disability Rate (5 Yr ACS)`

The workbook contains national ZCTA data. The notebook trains on the national
ZCTA panel to improve model stability, then defaults to forecasting rows where
`Food Bank 1` contains `Feeding Tampa Bay`.

## Forecast Unit

The forecast unit is a ZIP-county row, not a unique ZIP alone.

The row key is:

```text
row_id = State FIPS + County FIPS + ZCTA
```

This is intentional because some ZCTAs cross county boundaries and therefore
appear as more than one ZIP-county row in the Map the Meal Gap workbook.

## Observed Years and Forecast Years

The observed ZCTA panel currently contains:

```text
2020, 2021, 2022, 2023
```

The latest observed year is 2023. The notebook forecasts eight following years:

```text
2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031
```

## Modeling Approach

The updated methodology has four major stages.

### 1. Prepare the ZCTA Panel

The notebook reads the `ZCTA` sheet from `MMG_2025.xlsx`, normalizes column
names, and parses rates, counts, and dollar values into numeric form.

The core modeling variables are:

- prior-year food insecurity rate
- unemployment rate
- poverty rate
- percent Black
- percent Hispanic
- log median income
- homeownership rate
- disability rate
- centered year

Median income is log transformed:

```text
log_median_income = log(median_income)
```

Missing feature values are filled first using state-level medians and then, if
needed, overall medians.

### 2. Train a ZIP-Year Transition Model

The main model predicts a ZIP-county row's food insecurity rate in year `t` from
its previous-year food insecurity rate and current-year local drivers.

Conceptually:

```text
food_insecurity_rate[t] =
    f(
      food_insecurity_rate[t-1],
      unemployment_rate[t],
      poverty_rate[t],
      percent_black[t],
      percent_hispanic[t],
      log_median_income[t],
      homeownership_rate[t],
      disability_rate[t],
      year_centered[t]
    )
```

The implementation uses a weighted ridge regression trained on national ZCTA
year-to-year transitions. Rows are weighted by population so that very small
geographies do not dominate the fit.

The training target is:

```text
Overall Food Insecurity Rate
```

The main training rows are ZCTA records with:

- an observed current-year food insecurity rate
- an observed prior-year food insecurity rate
- a non-missing population

### 3. Validate Locally on Feeding Tampa Bay Rows

The notebook includes a local validation section for the target service area.
This validation fits a temporary transition model using only pre-latest-year
transitions, then predicts the latest observed year for Feeding Tampa Bay rows.

With the current workbook, the latest observed year is 2023, so the validation
uses earlier transitions to predict 2023 food insecurity rates. It reports:

- row count
- unique ZCTA count
- population-weighted MAE
- population-weighted RMSE
- population-weighted mean error
- population-weighted actual food insecurity rate
- population-weighted predicted food insecurity rate

The notebook also displays the largest local misses so those rows can be
reviewed for data quality, model fit, or possible local calibration needs. This
validation is diagnostic only; it does not change the production forecast model.

### 4. Fill Missing 2023 Baselines

Some latest-year Feeding Tampa Bay ZIP-county rows are missing an observed 2023
food insecurity rate. For those rows, the notebook uses a separate same-year
ridge model to estimate a 2023 fallback baseline.

The output records the baseline source in:

```text
food_insecurity_baseline_source
```

Current labels are:

- `mmg_zcta_2023_observed`: the 2023 food insecurity rate came directly from
  `MMG_2025.xlsx`.
- `modeled_2023_fallback`: the 2023 food insecurity rate was estimated because
  the workbook had a missing value for that ZIP-county row.

### 5. Project Future Drivers

For each forecast ZIP-county row, the notebook projects future values of local
drivers using simple row-level linear trends from the observed 2020-2023 panel.

Projected drivers include:

- population
- unemployment rate
- poverty rate
- percent Black
- percent Hispanic
- log median income
- homeownership rate
- disability rate

Rate variables are clipped to valid ranges. Median income is forecast in log
space and then converted back to dollars:

```text
median_income = exp(log_median_income)
```

This driver forecast is intentionally simple. It should be replaced with
external economic and demographic forecasts when those are available.

## Recursive Forecasting

The notebook forecasts food insecurity recursively.

For 2024, the lagged food insecurity rate is the observed or fallback 2023
baseline:

```text
lag_food_insecurity_rate[2024] = food_insecurity_rate_2023_used
```

For later years, the lagged value is the prior year's prediction:

```text
lag_food_insecurity_rate[year] =
    predicted_food_insecurity_rate[year - 1]
```

The trained transition model is then applied for each forecast year:

```text
predicted_food_insecurity_rate[year] =
    transition_model(
      lag_food_insecurity_rate[year],
      projected_driver_values[year]
    )
```

Predicted rates are clipped to the range 0% to 95%.

Predicted counts are calculated as:

```text
predicted_food_insecure_persons =
    predicted_food_insecurity_rate * projected_population
```

## Output

The notebook writes the forecast to:

`data/processed/zipcode_food_insecurity_forecast_mmg_panel_2024_2031.csv`

The output contains one row per ZIP-county-year. With the current Feeding Tampa
Bay filter, the output has:

```text
259 ZIP-county rows * 8 forecast years = 2,072 rows
```

Important output fields include:

- `row_id`
- `state_fips`
- `county_fips`
- `zcta`
- `Geography`
- `County, State`
- `State`
- `Food Bank 1 ID`
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

## Uncertainty Bands

The notebook creates simple residual-based uncertainty bands using the standard
deviation of training residuals from the transition model:

```text
uncertainty_band_low =
    predicted_food_insecurity_rate - 1.64 * residual_standard_deviation

uncertainty_band_high =
    predicted_food_insecurity_rate + 1.64 * residual_standard_deviation
```

These bands are useful diagnostics, but they should not be interpreted as formal
prediction intervals.

## Key Assumptions

The methodology relies on the following assumptions:

- The national ZCTA panel is useful for learning ZIP-level food insecurity
  transition patterns.
- Feeding Tampa Bay ZIP-county rows follow broadly similar relationships between
  food insecurity and the included economic/demographic drivers.
- Recent 2020-2023 linear trends are a reasonable baseline for projecting local
  driver variables over 2024-2031.
- Recursive forecasting is acceptable for eight years, even though uncertainty
  compounds over time.
- ZIP-county rows are the correct geographic unit when ZCTAs cross county
  boundaries.

## Limitations

The current methodology has several limitations:

- No observed post-2023 food insecurity rates are used.
- Future driver values are linear extrapolations, not externally validated
  forecasts.
- The model is predictive, not causal.
- Recursive forecasts can amplify model error over longer horizons.
- Very small population ZIP-county rows may produce unstable rates or counts.
- The uncertainty bands are residual diagnostics, not formal statistical
  prediction intervals.

## Recommended Future Improvements

If more data becomes available, the methodology should be improved in the
following order:

1. Replace linear driver extrapolations with external economic and demographic
   forecasts.
2. Add scenario forecasts, such as baseline, optimistic, and pessimistic
   unemployment or poverty paths.
3. Validate the model with additional historical years when newer Map the Meal
   Gap releases become available.
4. Consider more flexible panel models, such as gradient boosting or mixed
   effects models, if they improve time-based validation.
5. Calibrate ZIP-county predictions so they aggregate consistently to known or
   projected county totals.
