USE ROLE CAPONETEAM;
USE DATABASE FTB;
USE SCHEMA SILVER;

--Cleaning Table Zip_Code in Bronze and moving to Silver;

CREATE OR REPLACE DYNAMIC TABLE FTB.SILVER.ZIP_CODE
(
    County_FIPS,
    zcta,
    geography,
    County_State,
    state,
    Year,
    FoodBank_1_ID,
    FoodBank_1_Name,
    FoodBank_2_ID,
    FoodBank_2_Name,
    Total_Pop_5Y_ACS,
    Overall_Food_Insecurity_Rate,
    Num_Food_Insecure_Persons_Overall,
    Unemployment_Rate_1Yr_BLS,
    Poverty_Rate_5Yr_ACS,
    Percent_Black_5Yr_ACS,
    Percent_Hispanic_5Yr_ACS,
    Median_Income_5Yr_ACS,
    Homeownership_Rate_5Yr_ACS,
    Disability_Rate_5Yr_ACS
)
    TARGET_LAG = 'DOWNSTREAM'
    REFRESH_MODE = AUTO
    INITIALIZE = ON_CREATE
    WAREHOUSE = DEV01_TESTING
AS
SELECT
    NULLIF(TRIM("County FIPS"),'') AS County_FIPS,
    NULLIF(TRIM("ZCTA"),'') AS zcta,
    NULLIF(TRIM("Geography"),'') AS geography,
    NULLIF(TRIM("County, State"),'') AS County_State,
    NULLIF(TRIM("State"),'') AS state,
    TRY_CAST(NULLIF(TRIM("Year"),'') AS NUMBER) AS Year,
    TRY_CAST(NULLIF(TRIM("Food Bank 1 ID"),'') AS INTEGER) AS FoodBank_1_ID,
    NULLIF(TRIM("Food Bank 1"),'') AS FoodBank_1_Name,
    TRY_CAST(NULLIF(TRIM("Food Bank 2 ID"),'') AS INTEGER) AS FoodBank_2_ID,
    NULLIF(TRIM("Food Bank 2"),'') AS FoodBank_2_Name,
    TRY_CAST(REPLACE(NULLIF(TRIM("Total Population (5 Year ACS)"),''),',','') AS NUMBER(18,2)) AS Total_Pop_5Y_ACS,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Overall Food Insecurity Rate"),''),'%','') AS FLOAT)/100,3) AS Overall_Food_Insecurity_Rate,
    TRY_CAST(REPLACE(NULLIF(TRIM("# of Food Insecure Persons Overall"),''),',','') AS NUMBER(18,2)) AS Num_Food_Insecure_Persons_Overall,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Unemployment Rate (1 Yr BLS)"),''),'%','') AS FLOAT)/100,3) AS Unemployment_Rate_1Yr_BLS,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Poverty Rate (5 Yr ACS)"),''),'%','') AS FLOAT)/100,3) AS Poverty_Rate_5Yr_ACS,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Percent Black (5 Yr ACS)"),''),'%','') AS FLOAT)/100,3) AS Percent_Black_5Yr_ACS,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Percent Hispanic (any race) (5 Year ACS)"),''),'%','') AS FLOAT)/100,3) AS Percent_Hispanic_5Yr_ACS,
    TRY_CAST(REPLACE(NULLIF(LTRIM("Median Income (5 Yr ACS)",'$'),''),',','') AS NUMBER(18,2)) AS Median_Income_5Yr_ACS,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Homeownership Rate (5 Yr ACS)"),''),'%','') AS FLOAT)/100,3) AS Homeownership_Rate_5Yr_ACS,
    ROUND(TRY_CAST(REPLACE(NULLIF(TRIM("Disability Rate (5 Yr ACS)"),''),'%','') AS FLOAT)/100,3) AS Disability_Rate_5Yr_ACS
FROM FTB.BRONZE.ZIP_CODE;


SELECT overall_food_insecurity_rate, unemployment_rate_1yr_bls, poverty_rate_5yr_acs, percent_black_5yr_acs, percent_hispanic_5yr_acs, median_income_5yr_acs, homeownership_rate_5yr_acs, disability_rate_5yr_acs
FROM PUBLIC.MMG.ZIP_CODE;
