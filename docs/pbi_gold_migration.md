# Repoint PBI_LOCAL.pbix to Snowflake (FTB.GOLD)

## Why

`PBI_LOCAL.pbix` currently loads all 9 tables from a local Excel file on someone's laptop:

```
Excel.Workbook(File.Contents("C:\Users\supri\Downloads\MMG FTB - Tableau.xlsx"), null, true)
```

That means the report can only refresh on that one machine, and anyone else opening it gets a broken/missing data source. The same data now lives in Snowflake, in the `FTB.GOLD` schema — cleaned, typed, and refreshable by anyone with access. This doc walks through switching each table's source over.

You'll need **Power BI Desktop on Windows** for all of this — there's no way to do it from the web app or on Mac/Linux.

## What you need before starting

- `PBI_LOCAL.pbix` open in Power BI Desktop.
- Snowflake credentials for the service account `POWER_BI_SVC_USER`. It authenticates via key-pair (not a password) as role `POWER_BI_READER_ROLE`, which has read-only `SELECT` access to everything in `FTB.GOLD`. Ask Seth for the private key file if you don't already have it — it isn't included in this doc.
- Connection details you'll be prompted for the first time Power BI connects:
  - **Server**: `a6484859099771-occ89006.snowflakecomputing.com`
  - **Warehouse**: `POWER_BI_WH`
  - **Role**: `POWER_BI_READER_ROLE`

## Part 1 — Swap the 9 table sources

For each table listed below:

1. In Power BI Desktop, click **Transform data** (Home ribbon) to open the Power Query editor.
2. In the Queries pane on the left, click the table.
3. Click **Advanced Editor** (Home ribbon, in the Power Query editor).
4. Select all the existing text and delete it, then paste in the replacement M code shown below for that table.
5. Click **Done**.

The first table you do this for will pop up a credential prompt — enter the Snowflake connection details above and the `POWER_BI_SVC_USER` credential. After that, the rest of the tables reuse the same saved connection automatically and won't prompt again.

Once all 9 tables are switched, click **Refresh** in the Power Query editor to confirm everything loads without errors, then **Close & Apply**.

### Table mapping

| Old table (Excel) | New table (Snowflake `FTB.GOLD`) | Notes |
|---|---|---|
| Agencies | `AGENCIES` | `ZipText` custom column recreated |
| Alice Report | `ALICE_REPORT` | straight swap |
| Child Food Insecurity (MMG sour | `CHILD_FOOD_INSECURITY_MMG_SOUR` | straight swap |
| Data Sources | `DATA_SOURCES` | straight swap |
| ftb census track | `FTB_CENSUS_TRACK` | `GeoIdText` column + null-filter recreated |
| School Pantries | `SCHOOL_PANTRIES` | **structural change — see note below** |
| School Pantries address | `SCHOOL_PANTRIES_ADDRESS` | straight swap |
| Sheet3 | `ZIP_COUNTY_TRACT_CITY_LOOKUP` | **structural change — see note below** |
| ZIP CODES | `ZIP_CODES` | straight swap |

For the "straight swap" tables, all the old type-casting and header-promotion steps are gone — Snowflake already returns correctly typed columns, and blank rows / junk trailing columns were already cleaned up when these tables were loaded into `FTB.GOLD`.

---

### Agencies

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    AGENCIES_Table = GOLD_Schema{[Name="AGENCIES",Kind="Table"]}[Data],
    #"Added Custom" = Table.AddColumn(AGENCIES_Table, "ZipText", each Text.PadStart(Number.ToText(Number.Round([ZIP_CODE],0),"F0"),5,"0"))
in
    #"Added Custom"
```

### Alice Report

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    ALICE_REPORT_Table = GOLD_Schema{[Name="ALICE_REPORT",Kind="Table"]}[Data]
in
    ALICE_REPORT_Table
```

### Child Food Insecurity (MMG sour

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    CHILD_FOOD_INSECURITY_Table = GOLD_Schema{[Name="CHILD_FOOD_INSECURITY_MMG_SOUR",Kind="Table"]}[Data]
in
    CHILD_FOOD_INSECURITY_Table
```

### Data Sources

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    DATA_SOURCES_Table = GOLD_Schema{[Name="DATA_SOURCES",Kind="Table"]}[Data]
in
    DATA_SOURCES_Table
```

### ftb census track

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    FTB_CENSUS_TRACK_Table = GOLD_Schema{[Name="FTB_CENSUS_TRACK",Kind="Table"]}[Data],
    #"Added Custom" = Table.AddColumn(FTB_CENSUS_TRACK_Table, "GeoIdText", each Number.ToText(Number.Round([GEOID],0),"F0")),
    #"Filtered Rows" = Table.SelectRows(#"Added Custom", each ([COUNTY] <> null) and ([COUNTY_SUBDIVISION] <> null))
in
    #"Filtered Rows"
```

### School Pantries

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    SCHOOL_PANTRIES_Table = GOLD_Schema{[Name="SCHOOL_PANTRIES",Kind="Table"]}[Data]
in
    SCHOOL_PANTRIES_Table
```

> **Structural change**: the old query exposed generic `Column1`..`Column26` (no real header row). The new table has real column names instead: `SCHOOL_PANTRY, AGENCY_NUMBER, ZIP_CODES, COUNTY, MONTH_2025_01 .. MONTH_2025_12, TOTAL_POUNDS, TOTAL_MEALS`. The 8 trailing columns that were always blank in the original sheet are gone entirely. **Any existing visual built against `Column1`..`Column26` will show as broken/missing after this change and needs to be manually rebound to the correct new column.**

### School Pantries address

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    SCHOOL_PANTRIES_ADDRESS_Table = GOLD_Schema{[Name="SCHOOL_PANTRIES_ADDRESS",Kind="Table"]}[Data]
in
    SCHOOL_PANTRIES_ADDRESS_Table
```

### Sheet3 → ZIP_COUNTY_TRACT_CITY_LOOKUP

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    ZIP_COUNTY_TRACT_CITY_LOOKUP_Table = GOLD_Schema{[Name="ZIP_COUNTY_TRACT_CITY_LOOKUP",Kind="Table"]}[Data]
in
    ZIP_COUNTY_TRACT_CITY_LOOKUP_Table
```

> **Structural change**: this table has also been renamed (was `Sheet3`, no real name to begin with). The old query exposed generic `Column1`..`Column4`; the new table has real column names: `ZIP, COUNTY, CENSUS_TRACT_GEOID, CITY`. This sheet had no header row in the original Excel file, so the column meaning wasn't documented anywhere before now. **Any existing visual built against `Column1`..`Column4` needs to be manually rebound.**

### ZIP CODES

```m
let
    Source = Snowflake.Databases("a6484859099771-occ89006.snowflakecomputing.com", "POWER_BI_WH", [Role="POWER_BI_READER_ROLE"]),
    FTB_Database = Source{[Name="FTB",Kind="Database"]}[Data],
    GOLD_Schema = FTB_Database{[Name="GOLD",Kind="Schema"]}[Data],
    ZIP_CODES_Table = GOLD_Schema{[Name="ZIP_CODES",Kind="Table"]}[Data]
in
    ZIP_CODES_Table
```

---

## Part 2 — Publish and share so it works for everyone, not just your machine

Getting the file itself pointed at Snowflake only fixes it locally. To make the report actually usable by the team from the Power BI Service (web), a few more steps:

1. **Publish**: in Power BI Desktop, **File → Publish → Publish to Power BI**, and pick the destination workspace. This uploads the file as a dataset + report into that workspace.

2. **The shared Snowflake connection already exists** — no need to create one. In the Power BI Service, gear icon (top right) → **Manage connections and gateways** → **Connections** tab, there's already an entry named `a6484859099771-occ89006.snowflakecomputing.com;POWER_BI_WH` (Snowflake, KeyPair auth, created Aug 3, 2026). That's the one to use.

3. **Share access to that connection**: click it, then **Manage users** (or the `...` menu → **Manage users**), and add whoever needs to be able to use it. This is the step that's easy to miss — it's separate from sharing the report itself, and it's what lets other people's copies of the dataset refresh without them needing their own Snowflake login or ever seeing the actual credential.

4. **Point the dataset at that connection**: back in the workspace, open the dataset's **Settings** → **Gateway and cloud connections** section, and map the Snowflake data source to the existing connection from step 2 (instead of leaving it as a personal one-off credential, if Power BI created one automatically when you first connected in Desktop).

5. **Test and schedule**: click **Refresh now** to confirm it works end-to-end. Then, still in dataset Settings, turn on **Scheduled refresh** and pick a cadence, so the report keeps pulling current `FTB.GOLD` data automatically instead of only updating when someone happens to open it in Desktop.

## Optional cleanup, once everything above is confirmed working

Each table's M code above repeats the same `Snowflake.Databases(...)` connection call. You can factor that into one shared query (e.g. name it `GoldSource`) that all 9 tables reference via `GoldSource{[Name="TABLENAME",Kind="Table"]}[Data]` instead — one place to update if the server, warehouse, or role ever changes, rather than nine.
