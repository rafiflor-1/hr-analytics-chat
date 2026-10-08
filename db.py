"""Data access layer for the HR chat agent.

Two interchangeable backends, chosen with the HR_BACKEND environment variable:

* "duckdb"    (default) - the Parquet files in ./data, loaded into an
                          in-memory DuckDB database. No credentials needed.
* "snowflake"           - the same tables in Snowflake, using a programmatic
                          access token (or password) from the environment.

Both expose the same three functions: dialect(), schema_text(), run_sql().
Only read-only queries are allowed.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
MAX_ROWS = 200  # rows returned to the model per query

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|replace|truncate|grant|revoke|"
    r"copy|put|get|call|attach|detach|install|load|export|import|pragma|set|use)\b",
    re.IGNORECASE,
)


class QueryError(Exception):
    """Raised for rejected or failing queries; the message is shown to the model."""


def backend() -> str:
    return os.getenv("HR_BACKEND", "duckdb").lower()


def dialect() -> str:
    return "Snowflake SQL" if backend() == "snowflake" else "DuckDB SQL (PostgreSQL-like)"


def _strip_literals_and_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate(sql: str) -> str:
    """Allow a single SELECT / WITH statement and nothing else."""
    cleaned = sql.strip().rstrip(";").strip()
    bare = _strip_literals_and_comments(cleaned)
    if ";" in bare:
        raise QueryError("Only one SQL statement is allowed per call.")
    if not re.match(r"^\s*(select|with)\b", bare, re.IGNORECASE):
        raise QueryError("Only SELECT queries are allowed.")
    hit = _FORBIDDEN.search(bare)
    if hit:
        raise QueryError(f"Keyword '{hit.group(0).upper()}' is not allowed: read-only access.")
    return cleaned


# --------------------------------------------------------------------------- DuckDB
@lru_cache(maxsize=1)
def _duck():
    import duckdb

    files = sorted(DATA_DIR.glob("*.parquet"))
    if not files:
        raise RuntimeError(
            f"No Parquet files in {DATA_DIR}. Run: python build_data.py <HR_Demo_Model.xlsx>"
        )
    con = duckdb.connect(":memory:")
    for f in files:
        path = str(f).replace("'", "''")
        con.execute(f"CREATE TABLE \"{f.stem}\" AS SELECT * FROM read_parquet('{path}')")
    # After loading, forbid any further file or network access from SQL.
    con.execute("SET enable_external_access = false")
    return con


def _duck_schema() -> dict[str, list[tuple[str, str]]]:
    rows = _duck().execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "ORDER BY table_name, ordinal_position"
    ).fetchall()
    out: dict[str, list[tuple[str, str]]] = {}
    for t, c, d in rows:
        out.setdefault(t, []).append((c, d))
    return out


# ------------------------------------------------------------------------ Snowflake
def _private_key_der() -> bytes | None:
    """Load the RSA private key for key-pair login, if one is configured.

    SNOWFLAKE_PRIVATE_KEY       - the PEM text itself (use this in Streamlit Secrets)
    SNOWFLAKE_PRIVATE_KEY_FILE  - path to the .p8 / .pem file (use this on a laptop)
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE - only if the key is encrypted
    """
    from cryptography.hazmat.primitives import serialization

    pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    path = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
    if not pem and path:
        pem = Path(path).expanduser().read_text()
    if not pem:
        return None
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = serialization.load_pem_private_key(
        pem.strip().replace("\\n", "\n").encode(),
        password=passphrase.encode() if passphrase else None,
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@lru_cache(maxsize=1)
def _snow():
    import snowflake.connector  # optional dependency

    auth: dict = {}
    key = _private_key_der()
    if key:
        auth["private_key"] = key  # key-pair authentication
    elif os.getenv("SNOWFLAKE_TOKEN"):
        auth["password"] = os.environ["SNOWFLAKE_TOKEN"]  # programmatic access token
    else:
        raise RuntimeError(
            "Snowflake backend selected but no credentials found. Set "
            "SNOWFLAKE_PRIVATE_KEY (or SNOWFLAKE_PRIVATE_KEY_FILE), or SNOWFLAKE_TOKEN."
        )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "HR_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "HR_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "HR"),
        role=os.getenv("SNOWFLAKE_ROLE") or None,
        client_session_keep_alive=True,  # keeps the session token fresh while the app is open
        **auth,
    )


# Snowflake errors that mean "this connection is dead, open a new one":
#   390114 authentication token has expired   390111 session token expired
#   390112 / 390195 session no longer exists  08001 / 250001 could not connect
_RECONNECT_MARKERS = (
    "token has expired",
    "session no longer exists",
    "session token",
    "390114",
    "390111",
    "390112",
)


def _needs_reconnect(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(m in text for m in _RECONNECT_MARKERS)


def _reset_snowflake() -> None:
    """Drop the cached connection so the next call logs in again."""
    try:
        _snow().close()
    except Exception:
        pass
    _snow.cache_clear()


def _snow_schema() -> dict[str, list[tuple[str, str]]]:
    cur = _snow().cursor()
    cur.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = CURRENT_SCHEMA() ORDER BY table_name, ordinal_position"
    )
    out: dict[str, list[tuple[str, str]]] = {}
    for t, c, d in cur.fetchall():
        out.setdefault(t, []).append((c.lower(), d))
    return out


def _snow_query(sql: str) -> pd.DataFrame:
    cur = _snow().cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1)
        return pd.DataFrame(rows, columns=[c[0].lower() for c in cur.description])
    finally:
        cur.close()


# --------------------------------------------------------------------------- public
@lru_cache(maxsize=1)
def schema() -> dict[str, list[tuple[str, str]]]:
    return _snow_schema() if backend() == "snowflake" else _duck_schema()


def schema_text() -> str:
    lines = []
    for table, cols in schema().items():
        lines.append(f"{table}(" + ", ".join(f"{c} {d}" for c, d in cols) + ")")
    return "\n".join(lines)


def run_sql(sql: str) -> pd.DataFrame:
    """Validate and run one read-only query; returns at most MAX_ROWS rows."""
    cleaned = validate(sql)
    try:
        if backend() == "snowflake":
            try:
                df = _snow_query(cleaned)
            except Exception as exc:
                if not _needs_reconnect(exc):
                    raise
                _reset_snowflake()  # expired session: log in again and retry once
                df = _snow_query(cleaned)
        else:
            df = _duck().execute(cleaned).fetch_df_chunk()  # first chunk is plenty
            df = df.head(MAX_ROWS + 1)
    except QueryError:
        raise
    except Exception as exc:  # surface the database error to the model so it can retry
        raise QueryError(f"{type(exc).__name__}: {exc}") from exc
    df.attrs["truncated"] = len(df) > MAX_ROWS
    return df.head(MAX_ROWS)
