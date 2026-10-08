# HR Data Chat

A "chat with your data" agent for the HR analytics assignment. You ask a question in
plain English; Claude writes SQL against the HR tables, runs it, and answers with the
numbers. Every answer has a "Show the SQL" panel so the result can be checked.

It reads the same Snowflake schema as the two Tableau dashboards (Attendance Anomalies,
Retention and Turnover Risk) and uses the same metric definitions, so the answers agree
with them. The deployed app queries Snowflake live; without Snowflake settings it falls
back to a local extract of the same tables, so it also runs on a laptop with no database
access.

## Run it

Requires Python 3.10+ and an Anthropic API key.

```bash
cd hr_agent
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...       # Windows PowerShell: $env:ANTHROPIC_API_KEY="..."
streamlit run app.py
```

The browser opens at http://localhost:8501. Run like this, the app uses the local
extract in `data/`; see "Data source" below to point it at Snowflake.

## Sample questions

Expected answers were computed directly from the data.

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | What was the annual turnover rate in each year, and which year was worst? | 2019 18.5%, 2020 20.8%, 2021 21.2% (worst), 2022 17.8%, 2023 14.2%, 2024 19.2%, 2025 17.7%, 2026 13.5% (nine months only) |
| 2 | Which departments have the most high-risk active employees? | 7 in total: Engineering 4, Sales 3 |
| 3 | Who are the top 5 employees by excessive-overtime days? | Renana Barak (Finance) 162, Ayala Katz (Operations) 157, Erez Elbaz (Engineering) 109, Maya Gabay (HR) 94, Gilad Malka (Product) 78 |
| 4 | Which department has the highest late-arrival rate, and how does it compare to the company average? | Sales at 8.3%, against 4.5% company-wide |
| 5 | What are the top reasons people leave? | Career Growth 75, Better Compensation 73, Work-Life Balance 68, Performance 52 (involuntary), out of 366 exits |

Follow-up questions work too, for example "and only for Engineering?".

## How it works

```
question -> Claude (system prompt = schema + metric definitions)
                 |  tool call: run_sql(sql)
                 v
            db.py: validate (single SELECT only) -> DuckDB or Snowflake
                 |  rows as CSV
                 v
            Claude -> answer in plain language (+ SQL shown in the UI)
```

- `app.py` - Streamlit chat interface.
- `agent.py` - the agent loop, system prompt and metric definitions.
- `db.py` - data access and the read-only guard.
- `build_data.py` - converts the Excel workbook into the Parquet files in `data/`.
- `data/` - one Parquet file per table (a snapshot of the Snowflake schema).

Safety: only a single `SELECT`/`WITH` statement is accepted, write keywords are
rejected, at most 200 rows go back to the model, and DuckDB's file and network access
is switched off once the data is loaded.

## Deploying to Streamlit Community Cloud

1. Create a GitHub repository and upload everything in this folder, including `data/`.
   Never upload a real `secrets.toml`, `.env` or private key.
2. Sign in at https://share.streamlit.io with GitHub, choose **Create app**, pick the
   repository, branch `main`, and main file `app.py`.
3. Under **Advanced settings -> Secrets**, paste:

   ```toml
   ANTHROPIC_API_KEY = "your-anthropic-api-key"
   APP_PASSWORD = "a-password-for-reviewers"
   ```
   Add the Snowflake settings from "Data source" below to query Snowflake live.
4. Deploy. The app gets a public `https://<name>.streamlit.app` address.

`APP_PASSWORD` puts a password prompt in front of the app, so a leaked link cannot
spend the API credit. Each browser session is also limited to 40 questions
(`MAX_QUESTIONS_PER_SESSION`). Leave `APP_PASSWORD` unset to run without a prompt.

## Data source

By default the app queries the Parquet files in `data/` with DuckDB, so it needs no
database and no credentials besides `ANTHROPIC_API_KEY`. The caption under the app title
shows which source is in use.

The data is synthetic (661 employees, 2024-2025). It can be regenerated with
`tools/generate_hr_data.py`; `excel/HR_Demo_Model.xlsx` holds the same tables and views,
and `sql/` has the Snowflake DDL and views.

### Optional: Snowflake backend

Set `HR_BACKEND=snowflake` plus the settings below (environment variables, or Streamlit
Secrets). Never commit a private key.

```toml
HR_BACKEND = "snowflake"
SNOWFLAKE_ACCOUNT = "<account>"
SNOWFLAKE_USER = "<user>"
SNOWFLAKE_ROLE = "<role>"
SNOWFLAKE_PRIVATE_KEY = """
-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
"""
```

Warehouse, database and schema default to `HR_WH`, `HR_DB` and `HR`
(override with `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`).
The schema needs the views `V_EMPLOYEE_360`, `V_ATTENDANCE_DAILY` and `V_MISSING_LOGS`.
