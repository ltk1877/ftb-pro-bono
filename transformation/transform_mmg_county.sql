-- Dynamic table to clean and type-cast the Map the Meal Gap county dataset
CREATE OR REPLACE DYNAMIC TABLE public.silver.county
    TARGET_LAG = DOWNSTREAM
    WAREHOUSE = DEV01_TESTING
AS
SELECT
    "Year" AS year,
    "FIPS" AS fips,
    "State" AS state_abbreviation,
    SPLIT_PART("County, State", ', ', 1) AS county,
    SPLIT_PART("County, State", ', ', 2) AS state,
    "Food Bank 1 ID" AS food_bank_id,
    "Food Bank 1" AS food_bank,

    -- Demographics (strip commas from numbers, strip % from percentages)
    CAST(REPLACE("Total Population (5 Year ACS)", ',', '') AS INTEGER) AS total_population,
    CAST(REPLACE("Total Child Population (5 Year ACS)", ',', '') AS INTEGER) AS total_child_population,
    CAST(RTRIM("Percent Black (5 Yr ACS)", '%') AS DOUBLE) / 100 AS black_rate,
    CAST(RTRIM("Percent Hispanic (any race) (5 Year ACS)", '%') AS DOUBLE) / 100 AS hispanic_rate,
    CAST(RTRIM("Percent White, non-Hispanic (5 Year ACS)", '%') AS DOUBLE) / 100 AS white_non_hispanic_rate,

    -- Economic indicators
    CAST(RTRIM("Non-Undergrad Poverty Rate (5 Yr ACS)", '%') AS DOUBLE) / 100 AS poverty_rate,
    CAST(RTRIM("Unemployment Rate (1 Yr BLS)", '%') AS DOUBLE) / 100 AS unemployment_rate,
    CAST(RTRIM("Disability Rate (5 Yr ACS)", '%') AS DOUBLE) / 100 AS disability_rate,
    CAST(REPLACE(REPLACE("Median Income (5 Yr ACS)", '$', ''), ',', '') AS INTEGER) AS median_income,
    CAST(RTRIM("Homeownership Rate (5 Yr ACS)", '%') AS DOUBLE) / 100 AS homeownership_rate,

    -- Food insecurity - overall
    CAST(RTRIM("Overall Food Insecurity Rate", '%') AS DOUBLE) / 100 AS food_insecurity_rate,
    CAST(REPLACE("# of Food Insecure Persons Overall", ',', '') AS INTEGER) AS food_insecure_persons,

    -- Food insecurity - by race
    CAST(RTRIM("Food Insecurity Rate among Black Persons (all ethnicities)", '%') AS DOUBLE) / 100 AS food_insecurity_rate_black,
    CAST(RTRIM("Food Insecurity Rate among Hispanic Persons (any race)", '%') AS DOUBLE) / 100 AS food_insecurity_rate_hispanic,
    CAST(RTRIM("Food Insecurity Rate among White, non-Hispanic Persons", '%') AS DOUBLE) / 100 AS food_insecurity_rate_white,

    -- SNAP
    CAST(RTRIM("SNAP Threshold", '%') AS INTEGER) AS snap_threshold_pct,
    CAST(RTRIM("% FI ≤ SNAP Threshold", '%') AS DOUBLE) / 100 AS below_snap_rate,

    -- Child food insecurity
    CAST(RTRIM("Child Food Insecurity Rate", '%') AS DOUBLE) / 100 AS child_food_insecurity_rate,
    CAST(REPLACE("# of Food Insecure Children", ',', '') AS INTEGER) AS food_insecure_children,
    CAST(RTRIM("% food insecure children in HH w/ HH incomes below 185 FPL", '%') AS DOUBLE) / 100 AS food_insecure_children_below_185_fpl_rate,

    -- Cost and gap
    CAST(REPLACE(REPLACE("Cost Per Meal", '$', ''), ',', '') AS DOUBLE) AS cost_per_meal,
    "Weighted Index" AS weighted_index,
    CAST(REPLACE(REPLACE("Weighted weekly $ needed by FI", '$', ''), ',', '') AS DOUBLE) AS weighted_weekly_shortfall,
    CAST(REPLACE(REPLACE("Weighted Annual Food Budget Shortfall", '$', ''), ',', '') AS DOUBLE) AS annual_food_budget_shortfall,
    CAST(REPLACE("Annual Meal Gap", ',', '') AS INTEGER) AS annual_meal_gap,

    -- Geography
    "Rural-Urban Continuum Code (2013)" AS rural_urban_code_2013,
    "Rural-Urban Continuum Code (2023)" AS rural_urban_code_2023,
    "Census Region" AS census_region,
    "Census Division" AS census_division,
    "FNS Region" AS fns_region

FROM
    PUBLIC.MMG.COUNTY
