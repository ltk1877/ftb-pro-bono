# Changelog

## 2026-08-06 — Ceres (Business Central) historical data → ftb.bronze

One-time load of a full database extract from Ceres, the company's former Business Central ERP (now retired/no longer in use), into `ftb.bronze`. 1,404 tables, ~59.6M rows, loaded completely unchanged — raw source table and column names preserved exactly via quoted identifiers, types taken straight from Snowflake's Parquet schema inference. No renaming, cleanup, or type coercion; a separate future script will handle a bronze → silver transform.

- **Storage**: parquet files (one per table, from the original DB export) live permanently in S3 at `s3://snowflakestaging1-975050112931-us-east-1-an/raw/ceres/<table-name>/<table-name>.parquet`. Uploaded via the S3 console (browser drag-and-drop of the local per-table folder structure), not the AWS CLI.
- **Snowflake objects created**: external stage `ftb.bronze.ceres_stage` (uses the existing `s3_snowflakestaging1` storage integration, scoped to the `raw/ceres` prefix — deliberately a new stage rather than widening the existing `ftb.bronze.s3_stage`, which is scoped to `raw/mmg` and backs a different, unrelated pipe-based pipeline) and file format `ftb.bronze.parquet_ff` (`TYPE = PARQUET, BINARY_AS_TEXT = FALSE` — needed because several BC tables have a raw SQL Server rowversion `timestamp` column with no logical Parquet type; Snowflake's default `BINARY_AS_TEXT = TRUE` tries to decode that as UTF-8 text and fails).
- **Load script**: `ingestion/load_ceres_bronze.py` — for each table, `CREATE OR REPLACE TABLE ... USING TEMPLATE (INFER_SCHEMA(...))` followed by `COPY INTO ... MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE`. Re-runnable if ever needed (idempotent via `CREATE OR REPLACE`), but not something that runs on a schedule.
- **No ingestion pipeline was established.** The existing bronze pattern for recurring sources (e.g. the `census_tract`/`county`/`zip_code` tables) uses `auto_ingest=true` Snowpipes that fire automatically when new files land in S3. Ceres is a historical, one-time extract from a decommissioned system — no new files will ever arrive at `raw/ceres/`, so a pipe would just be a permanent, inert object. A plain `COPY INTO` accomplished the same load without that overhead.

## 2026-08-03 — Snowflake → Power BI connection

Power BI connects to Snowflake as a dedicated service user, reading from `FTB.GOLD` only.

- **User**: `POWER_BI_SVC_USER`
- **Auth**: RSA key-pair (`SNOWFLAKE_JWT` authenticator), not a password. Private key: `power_bi_snowflake_key.p8`.
- **Role**: `POWER_BI_READER_ROLE` — read-only. Granted `USAGE` on database `FTB` and schema `FTB.GOLD`, plus `SELECT` on all current tables in `FTB.GOLD` and a **future grant** (`SELECT ON FUTURE TABLES/VIEWS/DYNAMIC TABLES IN SCHEMA FTB.GOLD`). The future grant means any new table landing in `GOLD` is automatically readable by Power BI — no follow-up grant needed when new gold tables are created.
- **Warehouse**: `POWER_BI_WH`
- **Account identifier**: use the full org-account form (`a6484859099771-occ89006`), not the bare account locator (`OCC89066`) — the locator alone 404s on login. Same issue was hit independently while setting up `FTB_LOADER_ROLE` on 2026-08-05.

This role is intentionally read-only and kept separate from `FTB_LOADER_ROLE` (used for CSV/Snowflake loading work), so a compromised or misbehaving BI connection can't write or drop anything.

Object names here (`FTB`, `GOLD`, `POWER_BI_*`) are kept uppercase to match what's actually deployed in the account already — see the note at the top of `docs/infrastructure.md`'s Consumption section on why this differs from the lowercase convention used for the newer Ceres pipeline above.

### Key rotation

RSA key-pair auth on Snowflake supports two active public keys per user (`RSA_PUBLIC_KEY` and `RSA_PUBLIC_KEY_2`), which allows zero-downtime rotation:

1. **Generate a new key pair** locally, without touching the currently active one:
   ```
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out power_bi_snowflake_key_new.p8
   openssl rsa -in power_bi_snowflake_key_new.p8 -pubout -out power_bi_snowflake_key_new.pub
   ```
2. **Add the new public key as the secondary slot** (the old key keeps working):
   ```sql
   ALTER USER POWER_BI_SVC_USER SET RSA_PUBLIC_KEY_2 = '<contents of power_bi_snowflake_key_new.pub, header/footer stripped>';
   ```
3. **Point Power BI at the new private key** (wherever the Snowflake connector/gateway credential is configured) and confirm it connects successfully. The old key is still valid as a fallback at this point, so this step is safe to test without an outage.
4. **Remove the old key** once the new one is confirmed working:
   ```sql
   ALTER USER POWER_BI_SVC_USER UNSET RSA_PUBLIC_KEY;
   ```
5. **Securely delete the old private key file** from disk (and anywhere else it was copied) — don't just leave it lying around after it's retired.

Optionally, promote the new key from the secondary to the primary slot afterward for tidiness (`SET RSA_PUBLIC_KEY = <new key>` then `UNSET RSA_PUBLIC_KEY_2`) — functionally identical either way, Snowflake accepts either slot at login.

Recommended cadence: rotate on a fixed schedule (e.g. every 90–180 days) or immediately if the key material is ever suspected to have leaked.
