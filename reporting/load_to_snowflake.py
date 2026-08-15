"""
Load every CSV in csv/ into a same-named table in ftb.gold.

Connects with key-pair auth using ftb_loader_svc_user / ftb_loader_role
(see provision_loader_role.sql). Each table is fully replaced on every run
(auto_create_table + overwrite), matching the semantics of "re-split the
workbook and re-sync the tables."

Required env vars:
  SNOWFLAKE_ACCOUNT     e.g. OCC89066
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

import pandas as pd
from cryptography.hazmat.primitives import serialization
from snowflake.connector import connect
from snowflake.connector.pandas_tools import write_pandas

CSV_DIR = Path("csv")
DATABASE = "ftb"
SCHEMA = "gold"

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


def main() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    csv_paths = sorted(CSV_DIR.glob("*.csv"))
    if not csv_paths:
        print(f"No CSVs found in {CSV_DIR}/", file=sys.stderr)
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

    try:
        for csv_path in csv_paths:
            table_name = csv_path.stem.lower()
            df = pd.read_csv(csv_path)
            success, num_chunks, num_rows, _ = write_pandas(
                conn,
                df,
                table_name=table_name,
                database=DATABASE,
                schema=SCHEMA,
                auto_create_table=True,
                overwrite=True,
                quote_identifiers=False,
            )
            status = "ok" if success else "FAILED"
            print(f"{csv_path.name} -> {DATABASE}.{SCHEMA}.{table_name}: {status} ({num_rows} rows)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
