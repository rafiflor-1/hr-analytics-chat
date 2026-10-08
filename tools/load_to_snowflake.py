#!/usr/bin/env python3
"""
Creates tables/views and loads the CSVs into Snowflake.
  pip install "snowflake-connector-python[pandas]"
Env vars: SF_ACCOUNT (e.g. orgname-account), SF_USER, SF_PASSWORD, SF_PASSCODE (6-digit TOTP from your authenticator app,
          valid ~30s, so set it right before running), SF_ROLE, SF_WAREHOUSE, SF_DATABASE, SF_SCHEMA (default HR_DEMO)
"""
import os, glob
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

DATE_COLS = {"birth_date", "hire_date", "termination_date", "event_date", "start_date", "end_date", "work_date", "snapshot_month_end"}
here = os.path.dirname(os.path.abspath(__file__))
kw = dict(account=os.environ["SF_ACCOUNT"], user=os.environ["SF_USER"], password=os.environ["SF_PASSWORD"])
for k, env in [("passcode", "SF_PASSCODE"), ("role", "SF_ROLE"), ("warehouse", "SF_WAREHOUSE"), ("database", "SF_DATABASE")]:
    if os.environ.get(env): kw[k] = os.environ[env]
schema = os.environ.get("SF_SCHEMA", "HR_DEMO")
con = snowflake.connector.connect(**kw)
cur = con.cursor()
cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}"); cur.execute(f"USE SCHEMA {schema}")
con.execute_string(open(os.path.join(here, "sql", "01_ddl.sql")).read())

order = ["dim_department", "dim_job", "dim_employee", "fact_lifecycle_event", "fact_absence",
         "fact_attendance", "fact_employee_monthly_snapshot", "fact_department_budget"]
for name in order:
    df = pd.read_csv(os.path.join(here, "data", f"{name}.csv"))
    for c in df.columns:
        if c in DATE_COLS: df[c] = pd.to_datetime(df[c]).dt.date.astype(object).where(df[c].notna(), None)
        elif c.endswith("_ts"): df[c] = pd.to_datetime(df[c])
        elif df[c].dtype == "float64" and df[c].dropna().mod(1).eq(0).all() and not c.startswith(("hours", "overtime", "tenure", "months_since")):
            df[c] = df[c].astype("Int64")
    df.columns = [c.upper() for c in df.columns]
    ok, _, nrows, _ = write_pandas(con, df, name.upper(), schema=schema.upper(), use_logical_type=True, quote_identifiers=False)
    print(f"{name.upper():34s} loaded={ok} rows={nrows:,}")

con.execute_string(open(os.path.join(here, "sql", "02_views.sql")).read())
print("Views created. Sanity:", cur.execute("SELECT COUNT(*) FROM V_EMPLOYEE_360").fetchone())
con.close()
