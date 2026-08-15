"""
One-time historical load of the Ceres (Business Central) parquet export into
ftb.bronze, completely unchanged: table names and column names are preserved
exactly as extracted (quoted identifiers), no renaming or type coercion
beyond what Snowflake's own Parquet schema inference does. A later script
transforms bronze -> silver with cleaned-up names.

Source of truth for what to load is data/ceres/<table>/<table>.parquet
locally (matches what was uploaded to the ceres_stage S3 prefix 1:1), so we
don't need AWS credentials here -- Snowflake reads the files itself via the
stage's storage integration.

Required env vars:
  SNOWFLAKE_ACCOUNT     e.g. myorg-myaccount
  SNOWFLAKE_USER        e.g. ftb_loader_svc_user
  SNOWFLAKE_PRIVATE_KEY_PATH   path to ftb_loader_svc_key.p8
  SNOWFLAKE_WAREHOUSE   e.g. power_bi_wh
  SNOWFLAKE_ROLE        e.g. ftb_loader_role

Optional:
  SNOWFLAKE_PRIVATE_KEY_PASSPHRASE   only if the .p8 is encrypted
"""

import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from snowflake.connector import connect

LOCAL_TABLE_DIR = Path("data/ceres")
DATABASE = "ftb"
SCHEMA = "bronze"
STAGE = "ftb.bronze.ceres_stage"
FILE_FORMAT = "ftb.bronze.parquet_ff"

REQUIRED_ENV_VARS = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PRIVATE_KEY_PATH",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_ROLE",
]


def load_private_key(path: str, passphrase: str | None) -> bytes:
    with open(path, "rb") as f:
        key_bytes = f.read()
    private_key = serialization.load_pem_private_key(
        key_bytes,
        password=passphrase.encode() if passphrase else None,
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_stage_path(table: str) -> str:
    escaped = table.replace("'", "''")
    return f"'@{STAGE}/{escaped}/'"


def main() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    table_names = sorted(p.name for p in LOCAL_TABLE_DIR.iterdir() if p.is_dir())
    if not table_names:
        print(f"No table folders found in {LOCAL_TABLE_DIR}/", file=sys.stderr)
        sys.exit(1)

    private_key_der = load_private_key(
        os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
    )

    conn = connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=private_key_der,
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        role=os.environ["SNOWFLAKE_ROLE"],
        database=DATABASE,
        schema=SCHEMA,
    )
    cur = conn.cursor()

    failures = []
    try:
        for i, table in enumerate(table_names, 1):
            qtable = quote_ident(table)
            stage_path = quote_stage_path(table)
            try:
                cur.execute(f"""
                    CREATE OR REPLACE TABLE {DATABASE}.{SCHEMA}.{qtable}
                      USING TEMPLATE (
                        SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
                        FROM TABLE(
                          INFER_SCHEMA(LOCATION=>{stage_path}, FILE_FORMAT=>'{FILE_FORMAT}')
                        )
                      )
                """)
                cur.execute(f"""
                    COPY INTO {DATABASE}.{SCHEMA}.{qtable}
                    FROM {stage_path}
                    FILE_FORMAT = (FORMAT_NAME = '{FILE_FORMAT}')
                    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
                """)
                result = cur.fetchall()
                rows_loaded = sum(r[3] for r in result) if result else 0
                print(f"[{i}/{len(table_names)}] {table}: ok ({rows_loaded} rows)")
            except Exception as e:
                print(f"[{i}/{len(table_names)}] {table}: FAILED -> {e}", file=sys.stderr)
                failures.append(table)
    finally:
        conn.close()

    if failures:
        print(f"\n{len(failures)} table(s) failed:", file=sys.stderr)
        for t in failures:
            print(f"  - {t}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
