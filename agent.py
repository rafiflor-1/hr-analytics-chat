"""Text-to-SQL agent: Claude answers HR questions by querying the data itself.

The model is given one tool, run_sql. It writes a query, reads the result,
optionally queries again, and then answers in plain language. Every query it
ran is returned alongside the answer so the user can check the work.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import anthropic
import pandas as pd

import db

MODEL = os.getenv("HR_AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 8  # tool round-trips per question
AS_OF_DATE = "2026-09-30"  # last date in the data set

SYSTEM_PROMPT = """You are an HR analytics assistant for a fictional company (ACME demo data).
You answer questions by querying the HR database with the run_sql tool, then explaining
the result in plain language. The same data feeds two Tableau dashboards
("Attendance Anomalies" and "Retention and Turnover Risk"), so your numbers must agree
with them: use the metric definitions below exactly.

SQL dialect: {dialect}. Read-only: a single SELECT (or WITH ... SELECT) per call.
The data ends on {as_of}; treat that as "today". Attendance data starts 2024-01-01,
monthly snapshots start 2019-01-31. Salaries are monthly, in ILS.

## Tables
{schema}

## How the tables relate
- DIM_EMPLOYEE is the hub: one row per employee (active and terminated).
  department_id -> DIM_DEPARTMENT, job_id -> DIM_JOB, manager_id -> DIM_EMPLOYEE.employee_id.
- FACT_EMPLOYEE_MONTHLY_SNAPSHOT: one row per employee per month-end while employed.
- FACT_LIFECYCLE_EVENT: hires, promotions, salary changes, transfers, terminations.
- FACT_ABSENCE: one row per leave period (vacation, sick leave, unpaid).
- FACT_DEPARTMENT_BUDGET: one row per department per fiscal year.
- V_ATTENDANCE_DAILY: one row per employee per worked day, with anomaly flags (0/1).
- V_EMPLOYEE_360: one row per employee with department, job, tenure and risk fields
  already joined. Prefer it over joining DIM tables yourself.
- V_MISSING_LOGS: working days with no attendance record for an active employee.

## Metric definitions (match the dashboards)
- Annual turnover rate = SUM(terminated_in_month) / (SUM(is_active_eom) / COUNT(DISTINCT snapshot_month_end)),
  i.e. leavers divided by average month-end headcount, grouped by year of snapshot_month_end.
  2026 covers only nine months, so say so when you report it.
- Headcount at a date = SUM(is_active_eom) for that snapshot_month_end.
- Active employees: employment_status = 'Active'. Leavers: employment_status = 'Terminated'
  (termination_type is 'Resignation' or 'Involuntary').
- Flight risk: risk_score (0-100) and risk_band ('Low','Medium','High') in V_EMPLOYEE_360;
  only meaningful for active employees, so always filter employment_status = 'Active'.
- Attendance anomaly flags in V_ATTENDANCE_DAILY: is_late_arrival, is_excessive_overtime,
  is_missing_clock_out, is_short_day, is_weekend_work. Counts = SUM(flag); rates = AVG(flag).
- Employee names are NOT unique (several people share a name). Always group and join by
  employee_id, and show the name and department next to it.
- compa_ratio = monthly_salary / salary_band_mid for the employee's job.

## How to work
1. Query before you answer. Never state a number you have not just retrieved.
2. If a query errors, read the message, fix the SQL and try again.
3. Keep result sets small: aggregate, and use LIMIT for lists (20 rows unless asked otherwise).
4. Answer first, in one or two sentences with the key numbers, then a short table if it helps.
   Round rates to one decimal place as percentages.
   Show average headcount as a whole number (a count of people), but compute rates from
   the unrounded average. If asked why it is not exact, explain that it is an average of
   month-end headcounts across the period.
5. State any assumption you made (time period, definition) in one line, in business
   language. Do not mention table, view or column names, SQL functions or expressions in
   the answer (write "excessive-overtime days", not SUM(is_excessive_overtime) or
   V_ATTENDANCE_DAILY). The SQL is shown to the user in a separate panel. Name a table or
   column only if the user asks about the data model or the query itself.
6. If the data cannot answer the question, say so plainly rather than guessing.
   Earlier answers in this conversation were each based on queries you ran at the time;
   only the answer text is kept in the history. Do not re-run them, re-verify them or
   comment on them unless the user asks. Answer only the current question.
7. Individual employees are fictional, so naming them is fine, but do not volunteer
   contact details (email, phone, birth date) unless explicitly asked.
"""

TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Run one read-only SQL query against the HR database and get the rows back as CSV. "
            f"At most {db.MAX_ROWS} rows are returned, so aggregate or LIMIT."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT or WITH statement."},
                "purpose": {
                    "type": "string",
                    "description": "One short sentence on what this query is for.",
                },
            },
            "required": ["sql"],
        },
    }
]


@dataclass
class QueryRecord:
    sql: str
    purpose: str = ""
    result: pd.DataFrame | None = None
    error: str | None = None


@dataclass
class Answer:
    text: str
    queries: list[QueryRecord] = field(default_factory=list)


def system_prompt() -> str:
    return SYSTEM_PROMPT.format(dialect=db.dialect(), as_of=AS_OF_DATE, schema=db.schema_text())


def _result_for_model(df: pd.DataFrame) -> str:
    if df.empty:
        return "Query returned 0 rows."
    note = (
        f"\n(Truncated to the first {db.MAX_ROWS} rows; aggregate or add LIMIT.)"
        if df.attrs.get("truncated")
        else ""
    )
    return df.to_csv(index=False) + note


def ask(question: str, history: list[dict] | None = None, client: anthropic.Anthropic | None = None) -> Answer:
    """Answer one question. `history` is prior turns as [{'role','content'}] plain text."""
    client = client or anthropic.Anthropic()
    messages: list[dict] = list(history or []) + [{"role": "user", "content": question}]
    records: list[QueryRecord] = []

    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=system_prompt(),
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return Answer(text or "I could not produce an answer.", records)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            record = QueryRecord(sql=block.input.get("sql", ""), purpose=block.input.get("purpose", ""))
            try:
                record.result = db.run_sql(record.sql)
                content, is_error = _result_for_model(record.result), False
            except db.QueryError as exc:
                record.error = str(exc)
                content, is_error = f"ERROR: {exc}", True
            records.append(record)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}
            )
        messages.append({"role": "user", "content": tool_results})

    return Answer(
        "I ran out of query attempts before reaching an answer. Try a narrower question.", records
    )
