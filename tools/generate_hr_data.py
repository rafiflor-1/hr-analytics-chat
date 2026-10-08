#!/usr/bin/env python3
"""
Synthetic HR data generator (Israeli-style company, Sun-Thu work week, salaries in ILS/month).
Simulates employees month-by-month (2019-01 .. 2026-09) so that lifecycle events, attrition,
attendance and absences are internally consistent and contain discoverable signals:

  * Attrition risk rises with: short tenure, no promotion for 30+ months, pay below band (compa-ratio < 0.92),
    chronic overtime, Sales/Support departments, low performance.
  * Resigning employees take more sick leave in their last ~3 months.
  * ~4% of employees are chronic late arrivers, ~3% are chronic overtimers.
  * Customer Support has an overtime spike in Q4-2025.
  * Random anomalies: missing clock-outs, missing logs (no attendance + no leave), Fri/Sat work.

Output: ./data/*.csv   (run: python generate_hr_data.py)
"""
import os
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
SIM_START, TODAY = pd.Timestamp("2019-01-01"), pd.Timestamp("2026-09-30")
ABS_START, ATT_START = pd.Timestamp("2022-01-01"), pd.Timestamp("2024-01-01")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- reference data
DEPTS = [  # id, name, cost centre, salary multiplier, hiring weight, ladder L1..L5
    (1, "Engineering", "CC-100", 1.25, .30, ["Junior Software Engineer", "Software Engineer", "Senior Software Engineer", "Engineering Team Lead", "VP Engineering"]),
    (2, "Product", "CC-110", 1.15, .07, ["Associate Product Manager", "Product Manager", "Senior Product Manager", "Group Product Manager", "VP Product"]),
    (3, "Sales", "CC-200", 1.05, .18, ["Sales Development Rep", "Account Executive", "Senior Account Executive", "Sales Team Lead", "VP Sales"]),
    (4, "Marketing", "CC-210", 0.95, .07, ["Marketing Coordinator", "Marketing Specialist", "Senior Marketing Manager", "Marketing Team Lead", "VP Marketing"]),
    (5, "Customer Support", "CC-300", 0.75, .18, ["Support Agent", "Support Specialist", "Senior Support Specialist", "Support Team Lead", "VP Customer Success"]),
    (6, "Finance", "CC-400", 1.00, .05, ["Junior Accountant", "Accountant", "Senior Financial Analyst", "Finance Team Lead", "CFO"]),
    (7, "Human Resources", "CC-410", 0.90, .04, ["HR Coordinator", "HR Generalist", "Senior HR Business Partner", "HR Team Lead", "VP People"]),
    (8, "Operations", "CC-500", 0.85, .11, ["Operations Associate", "Operations Specialist", "Senior Operations Analyst", "Operations Team Lead", "VP Operations"]),
]
DEPT_MULT = {d[0]: d[3] for d in DEPTS}
DEPT_NAME = {d[0]: d[1] for d in DEPTS}
DEPT_NAME[9] = "Executive"
HIRE_DEPTS = [d[0] for d in DEPTS]
HIRE_W = np.array([d[4] for d in DEPTS])
DEPT_HAZ = {1: 1.0, 2: .9, 3: 1.25, 4: 1.0, 5: 1.35, 6: .7, 7: .7, 8: 1.05}
LEVEL_BASE = [11000, 15000, 20000, 27000, 42000, 90000]  # monthly ILS at 2019 prices

FN_F = "Noa Maya Yael Tamar Shira Michal Adi Lior Dana Rotem Talia Hila Ayala Gal Neta Shani Ofir Roni Efrat Keren Liat Sivan Meital Orly Inbar Yarden Renana Galit Hadas Nurit".split()
FN_M = "David Daniel Yossi Omer Itay Amit Eyal Guy Nadav Ron Tal Oren Avi Ido Yoav Shai Barak Nir Ofer Roee Assaf Erez Gilad Lior Moshe Eli Uri Alon Tomer Yaron".split()
LN = "Cohen Levi Mizrahi Peretz Biton Avraham Friedman Malka Azoulay Dahan Katz Shapiro Goldberg Ben-David Segal Amar Hadad Klein Weiss Golan Sharabi Barak Nachmias Oren Tzur Vaknin Shalom Rosen Erez Baruch Halevi Stern Carmi Zohar Navon Elbaz Gabay Ashkenazi Shamir Regev".split()
CITIES = ["Tel Aviv", "Ramat Gan", "Petah Tikva", "Kfar Saba", "Herzliya", "Raanana", "Netanya", "Rishon LeZion", "Holon", "Haifa", "Jerusalem", "Modiin", "Rehovot", "Hod HaSharon"]
OFFICES = ["Tel Aviv HQ", "Haifa Office", "Remote"]


def infl(d): return 1.03 ** ((d.year - 2019) + (d.month - 1) / 12)
def band_mid(dept, lvl, d): return LEVEL_BASE[lvl - 1] * DEPT_MULT.get(dept, 1.0) * infl(d)
def job_id(dept, lvl): return 41 if dept == 9 else (dept - 1) * 5 + lvl
def rand_day(lo, hi):
    return lo + pd.Timedelta(days=int(rng.integers(0, max(0, (hi - lo).days) + 1)))


# ---------------------------------------------------------------- simulation
emps, events, snaps = [], [], []


def ev(e, typ, date, fd=None, td=None, fj=None, tj=None, old=None, new=None, reason=None):
    events.append(dict(employee_id=e["id"], event_type=typ, event_date=date, from_department_id=fd, to_department_id=td,
                       from_job_id=fj, to_job_id=tj, old_monthly_salary=old, new_monthly_salary=new, reason=reason))


def make_emp(hire, dept, lvl, initial=False, head=False):
    eid = len(emps) + 1
    g = rng.choice(["F", "M"], p=[.48, .52])
    fn, ln = str(rng.choice(FN_F if g == "F" else FN_M)), str(rng.choice(LN))
    age = rng.uniform(36, 55) if head else rng.uniform(22, 52)
    ref = max(hire, SIM_START)
    salary = band_mid(dept, lvl, ref) * (rng.uniform(.95, 1.1) if head else (rng.uniform(.9, 1.15) if initial else rng.uniform(.88, 1.12)))
    late = rng.random() < .04
    e = dict(id=eid, first=fn, last=ln, gender=g, birth=hire - pd.Timedelta(days=int(age * 365.25)), hire=hire, dept=dept, level=lvl,
             salary=round(salary, -1), perf=int(np.clip(round(rng.normal(3.2, .8)), 1, 5)), ot_prop=float(rng.lognormal(0, .5)),
             chronic=bool(rng.random() < .03), late=bool(late), sick_prop=float(rng.lognormal(0, .4)),
             in_mean=float(rng.uniform(9.5, 10.2) if late else rng.uniform(8.0, 9.0)), last_promo=hire, term=None,
             term_type=None, exit_reason=None, dept_hist=[(hire, dept)], head=head, city=str(rng.choice(CITIES)),
             office=str(rng.choice(OFFICES, p=[.6, .15, .25])))
    emps.append(e)
    ev(e, "Hire", hire, td=dept, tj=job_id(dept, lvl), new=e["salary"], reason="Initial Load" if initial else "New Hire")
    return e


# seed population: CEO, 8 department heads, 231 staff
ceo = make_emp(pd.Timestamp("2012-03-01"), 9, 6, initial=True, head=True)
for d in DEPTS:
    make_emp(pd.Timestamp("2012-06-01") + pd.Timedelta(days=int(rng.integers(0, 1500))), d[0], 5, initial=True, head=True)
for _ in range(231):
    dpt = int(rng.choice(HIRE_DEPTS, p=HIRE_W))
    make_emp(SIM_START - pd.Timedelta(days=int(rng.integers(30, 2500))), dpt, int(rng.choice([1, 2, 3, 4], p=[.3, .3, .22, .18])), initial=True)

months = pd.date_range(SIM_START, TODAY, freq="MS")
for mi, m in enumerate(months):
    m_end = min(m + pd.offsets.MonthEnd(0), TODAY)
    if mi > 0:
        for _ in range(rng.poisson(3.6 + 0.02 * mi)):
            make_emp(rand_day(m, m_end), int(rng.choice(HIRE_DEPTS, p=HIRE_W)), int(rng.choice([1, 2, 3, 4], p=[.5, .28, .15, .07])))
    for e in [x for x in emps if x["term"] is None]:
        new_hire = e["hire"] >= m
        if not new_hire:
            lo = max(m, e["hire"] + pd.Timedelta(days=1))
            tenure = (m - e["hire"]).days / 30.4
            stag = (m - e["last_promo"]).days / 30.4
            last_ev = lo
            # annual review raise (April 1)
            if m.month == 4 and tenure >= 6 and rng.random() < .85:
                pct = max(0.0, .02 + .012 * (e["perf"] - 1) + rng.normal(0, .008))
                old = e["salary"]; e["salary"] = round(old * (1 + pct), -1)
                ev(e, "Salary Adjustment", m, fd=e["dept"], td=e["dept"], fj=job_id(e["dept"], e["level"]), tj=job_id(e["dept"], e["level"]),
                   old=old, new=e["salary"], reason="Annual Review")
            if not e["head"]:
                p = .010 + (.008 if e["perf"] >= 4 else 0) + (.004 if e["perf"] == 5 else 0)
                if e["level"] < 4 and stag >= 9 and rng.random() < p:
                    d = rand_day(lo, m_end); old = e["salary"]; oj = job_id(e["dept"], e["level"])
                    e["level"] += 1; e["salary"] = round(old * rng.uniform(1.08, 1.15), -1); e["last_promo"] = d; last_ev = max(last_ev, d)
                    ev(e, "Promotion", d, fd=e["dept"], td=e["dept"], fj=oj, tj=job_id(e["dept"], e["level"]), old=old, new=e["salary"], reason="Performance")
                if rng.random() < .004:
                    d = rand_day(lo, m_end); old = e["salary"]; od = e["dept"]
                    nd = int(rng.choice([x for x in HIRE_DEPTS if x != od]))
                    e["dept"] = nd; e["dept_hist"].append((d, nd)); e["salary"] = round(old * rng.uniform(1.0, 1.05), -1); last_ev = max(last_ev, d)
                    ev(e, "Department Transfer", d, fd=od, td=nd, fj=job_id(od, e["level"]), tj=job_id(nd, e["level"]), old=old, new=e["salary"], reason="Internal Mobility")
                # ---- attrition hazard
                compa = e["salary"] / band_mid(e["dept"], e["level"], m)
                high_ot = e["ot_prop"] > 1.6 or e["chronic"]
                stagnant = e["level"] < 4 and stag > 30
                h = .0100
                h *= 1.7 if tenure < 12 else (1.2 if tenure < 24 else 1.0)
                h *= 1.5 if stagnant else 1.0
                h *= 1.7 if compa < .92 else (.7 if compa > 1.08 else 1.0)
                h *= 1.4 if high_ot else 1.0
                h *= DEPT_HAZ[e["dept"]] * (1.3 if e["perf"] <= 2 else 1.0)
                if rng.random() < h and last_ev <= m_end and (e["hire"] + pd.Timedelta(days=30)) <= m_end:
                    td_ = rand_day(max(last_ev, e["hire"] + pd.Timedelta(days=30)), m_end)
                    invol = rng.random() < (.10 + (.25 if e["perf"] <= 2 else 0))
                    e["term"] = td_
                    if invol:
                        e["term_type"] = "Involuntary"; e["exit_reason"] = "Performance" if e["perf"] <= 2 else str(rng.choice(["Restructuring", "Performance"], p=[.7, .3]))
                    else:
                        e["term_type"] = "Resignation"
                        w = {"Better Compensation": 1 + (3 if compa < .92 else 0), "Career Growth": 1 + (3 if stagnant else 0),
                             "Work-Life Balance": 1 + (3 if high_ot else 0), "Relocation": .6, "Management Issues": .8, "Personal Reasons": 1}
                        ks = list(w); pw = np.array([w[k] for k in ks]); e["exit_reason"] = str(rng.choice(ks, p=pw / pw.sum()))
                    ev(e, "Termination", td_, fd=e["dept"], fj=job_id(e["dept"], e["level"]), old=e["salary"], reason=f'{e["term_type"]}: {e["exit_reason"]}')
        if e["term"] is None or e["term"] >= m:
            snaps.append(dict(snapshot_month_end=m_end, employee_id=e["id"], department_id=e["dept"], job_id=job_id(e["dept"], e["level"]),
                              monthly_salary=e["salary"], tenure_months=round(max(0, (m_end - e["hire"]).days) / 30.4, 1),
                              months_since_last_promotion=round(max(0, (m_end - e["last_promo"]).days) / 30.4, 1),
                              is_active_eom=0 if e["term"] is not None else 1, hired_in_month=int(new_hire),
                              terminated_in_month=int(e["term"] is not None)))

# ---------------------------------------------------------------- managers
active = [e for e in emps if e["term"] is None]
head_of = {e["dept"]: e["id"] for e in emps if e["head"] and e["level"] == 5}
leads = {}
for e in active:
    if e["level"] == 4 and not e["head"]:
        leads.setdefault(e["dept"], []).append(e["id"])
for e in emps:
    if e["head"]:
        e["manager"] = None if e["level"] == 6 else ceo["id"]
    elif e["level"] == 4:
        e["manager"] = head_of[e["dept"]]
    else:
        e["manager"] = int(rng.choice(leads[e["dept"]])) if leads.get(e["dept"]) else head_of[e["dept"]]

# ---------------------------------------------------------------- absences + attendance
WD = pd.date_range(ABS_START, TODAY)
WD = WD[WD.dayofweek.isin([6, 0, 1, 2, 3])]  # Sun-Thu
WD_ATT = WD[WD >= ATT_START]
abs_rows, att_frames = [], []


def gen_absences(e):
    lo = max(e["hire"] + pd.Timedelta(days=1), ABS_START)
    hi = e["term"] - pd.Timedelta(days=1) if e["term"] is not None else TODAY
    days = WD[(WD >= lo) & (WD <= hi)]
    n = len(days); used = np.zeros(n, bool)
    if n < 15:
        return days, used
    yrs = n / 230

    def place(kind, L, wlo=0):
        L = min(L, n - wlo)
        if L <= 0: return
        for _ in range(6):
            s = int(rng.integers(wlo, n - L + 1))
            if not used[s:s + L].any():
                used[s:s + L] = True
                abs_rows.append(dict(employee_id=e["id"], leave_type=kind, start_date=days[s], end_date=days[s + L - 1], working_days=L)); return

    rem = max(0, rng.normal(15, 4)) * yrs
    while rem >= 1:
        L = int(min(rem, rng.choice([1, 2, 3, 5, 5, 7, 10]))); place("Vacation", L); rem -= L
    for _ in range(rng.poisson(2.0 * e["sick_prop"] * yrs)):
        place("Sick Leave", int(rng.choice([1, 2, 3, 4], p=[.5, .3, .15, .05])))
    if e["term_type"] == "Resignation":  # pre-resignation sick-leave signal
        for _ in range(rng.poisson(1.5)):
            place("Sick Leave", int(rng.choice([1, 2, 3], p=[.5, .35, .15])), wlo=max(0, n - 65))
    if rng.random() < .05 * yrs:
        place("Unpaid Leave", int(rng.integers(3, 16)))
    return days, used


def att_rows(e, days, extra=False):
    k = len(days)
    if k == 0: return None
    hd = np.array([np.datetime64(h[0]) for h in e["dept_hist"]]); hdp = np.array([h[1] for h in e["dept_hist"]])
    dept = hdp[np.clip(np.searchsorted(hd, days.values, side="right") - 1, 0, None)]
    if extra:
        in_h = rng.uniform(9, 11, k); dur = rng.uniform(3, 7, k); ot = np.zeros(k)
    else:
        in_h = e["in_mean"] + rng.normal(0, .35, k); dur = rng.normal(8.4, .45, k)
        dur = np.where(rng.random(k) < .02, dur - rng.uniform(1.5, 3, k), dur)  # occasional short day
        p = np.full(k, .45 if e["chronic"] else .07 * e["ot_prop"])
        spike = (dept == 5) & (days >= "2025-10-01") & (days <= "2025-12-31")
        p[spike] = np.maximum(p[spike], .35)
        ot = (rng.random(k) < p) * rng.uniform(1, 3.5, k)
    total = dur + ot
    d64 = days.values.astype("datetime64[s]")
    cin = d64 + (in_h * 3600).astype("int64").astype("timedelta64[s]")
    cout = cin + (total * 3600).astype("int64").astype("timedelta64[s]")
    worked = np.round(total - .5, 2)
    miss = rng.random(k) < .012
    cout = cout.copy(); cout[miss] = np.datetime64("NaT")
    worked = np.where(miss, np.nan, worked)
    otime = np.where(miss, np.nan, np.where(worked - 8 >= .5, np.round(worked - 8, 2), 0.0))
    return pd.DataFrame(dict(employee_id=e["id"], department_id=dept, work_date=days.values, clock_in_ts=cin, clock_out_ts=cout,
                             hours_worked=worked, overtime_hours=otime))


for e in emps:
    days, used = gen_absences(e)
    absent = days[used]
    lo = max(e["hire"], ATT_START); hi = e["term"] if e["term"] is not None else TODAY
    d = WD_ATT[(WD_ATT >= lo) & (WD_ATT <= hi)]
    d = d[~d.isin(absent)]
    d = d[rng.random(len(d)) >= .006]  # ~0.6% silently missing logs (no attendance, no leave)
    f = att_rows(e, d)
    if f is not None: att_frames.append(f)
    if len(d) > 0:  # Fri/Sat work
        cal = pd.date_range(lo, hi); cal = cal[cal.dayofweek.isin([4, 5])]
        k2 = min(len(cal), rng.poisson((1.2 if e["chronic"] else .12) * len(d) / 21))
        if k2 > 0:
            f2 = att_rows(e, pd.DatetimeIndex(np.sort(rng.choice(cal.values, k2, replace=False))), extra=True)
            att_frames.append(f2)

# ---------------------------------------------------------------- build tables
dim_dept = pd.DataFrame([dict(department_id=d[0], department_name=d[1], cost_center=d[2], department_head_employee_id=head_of[d[0]]) for d in DEPTS]
                        + [dict(department_id=9, department_name="Executive", cost_center="CC-001", department_head_employee_id=ceo["id"])])
jobs = []
for d in DEPTS:
    for l, t in enumerate(d[5], 1):
        mid_ = round(band_mid(d[0], l, TODAY), -2)
        jobs.append(dict(job_id=job_id(d[0], l), job_title=t, job_level=l, job_family=d[1], department_id=d[0],
                         salary_band_min=round(mid_ * .8, -2), salary_band_mid=mid_, salary_band_max=round(mid_ * 1.25, -2)))
jobs.append(dict(job_id=41, job_title="Chief Executive Officer", job_level=6, job_family="Executive", department_id=9,
                 salary_band_min=80000, salary_band_mid=110000, salary_band_max=140000))
dim_job = pd.DataFrame(jobs)

dim_emp = pd.DataFrame([dict(
    employee_id=e["id"], first_name=e["first"], last_name=e["last"], gender=e["gender"], birth_date=e["birth"],
    email=f'{e["first"]}.{e["last"]}{e["id"]}@acme-demo.com'.lower().replace("'", ""),
    phone=f'05{rng.integers(0, 9)}-{rng.integers(1000000, 9999999)}', city=e["city"], office_location=e["office"],
    hire_date=e["hire"], termination_date=e["term"], termination_type=e["term_type"], exit_reason=e["exit_reason"],
    employment_status="Terminated" if e["term"] is not None else "Active", department_id=e["dept"], job_id=job_id(e["dept"], e["level"]),
    manager_id=e["manager"], monthly_salary=e["salary"], performance_rating=e["perf"]) for e in emps])

fact_ev = pd.DataFrame(events).sort_values(["event_date", "employee_id"]).reset_index(drop=True)
fact_ev.insert(0, "event_id", range(1, len(fact_ev) + 1))
fact_abs = pd.DataFrame(abs_rows).sort_values(["start_date", "employee_id"]).reset_index(drop=True)
fact_abs.insert(0, "absence_id", range(1, len(fact_abs) + 1))
fact_att = pd.concat(att_frames).sort_values(["work_date", "employee_id"]).reset_index(drop=True)
fact_att.insert(0, "attendance_id", range(1, len(fact_att) + 1))
fact_snap = pd.DataFrame(snaps)

# budgets: derive from actual headcount/payroll with planning noise
fs = fact_snap[fact_snap.is_active_eom == 1].copy(); fs["year"] = pd.to_datetime(fs.snapshot_month_end).dt.year
g = fs.groupby(["year", "department_id"]).agg(avg_hc=("employee_id", lambda s: len(s) / fs[fs.year == s.name[0]].snapshot_month_end.nunique() if False else np.nan)).reset_index()
per_month = fs.groupby(["year", "department_id", "snapshot_month_end"]).agg(hc=("employee_id", "count"), sal=("monthly_salary", "mean")).reset_index()
bud = per_month.groupby(["year", "department_id"]).agg(avg_hc=("hc", "mean"), avg_sal=("sal", "mean")).reset_index()
bud["budgeted_headcount"] = np.round(bud.avg_hc * rng.uniform(.95, 1.12, len(bud))).astype(int)
bud["annual_budget_ils"] = np.round(bud.budgeted_headcount * bud.avg_sal * 12 * 1.25 * rng.uniform(.95, 1.06, len(bud)), -3)
fact_bud = bud[["year", "department_id", "budgeted_headcount", "annual_budget_ils"]].rename(columns={"year": "fiscal_year"})
fact_bud.insert(0, "budget_id", range(1, len(fact_bud) + 1))

D, T = "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"
def fmt(df, dates=(), tss=()):
    df = df.copy()
    for c in dates: df[c] = pd.to_datetime(df[c]).dt.strftime(D)
    for c in tss: df[c] = pd.to_datetime(df[c]).dt.strftime(T)
    return df

tables = {
    "DIM_DEPARTMENT": dim_dept, "DIM_JOB": dim_job,
    "DIM_EMPLOYEE": fmt(dim_emp, ["birth_date", "hire_date", "termination_date"]),
    "FACT_LIFECYCLE_EVENT": fmt(fact_ev, ["event_date"]),
    "FACT_ABSENCE": fmt(fact_abs, ["start_date", "end_date"]),
    "FACT_ATTENDANCE": fmt(fact_att, ["work_date"], ["clock_in_ts", "clock_out_ts"]),
    "FACT_EMPLOYEE_MONTHLY_SNAPSHOT": fmt(fact_snap, ["snapshot_month_end"]),
    "FACT_DEPARTMENT_BUDGET": fact_bud,
}
KEEP_FLOAT = ("hours_worked", "overtime_hours", "tenure_months", "months_since_last_promotion")
for n, df in tables.items():
    for c in df.columns:  # whole numbers must be written as ints ("1", not "1.0") for Snowflake NUMBER(x,0)
        if df[c].dtype.kind == "f" and c not in KEEP_FLOAT:
            df[c] = df[c].astype("Int64")
    df.to_csv(os.path.join(OUT, f"{n.lower()}.csv"), index=False)
    print(f"{n:34s}{len(df):>9,} rows")

# sanity stats
snap = fact_snap.copy(); snap["yr"] = pd.to_datetime(snap.snapshot_month_end).dt.year
print("\nYear  avg headcount  leavers  turnover%")
for y, gdf in snap.groupby("yr"):
    hc = gdf[gdf.is_active_eom == 1].groupby("snapshot_month_end").size().mean()
    lv = gdf.terminated_in_month.sum()
    print(f"{y}  {hc:13.0f}  {lv:7d}  {100 * lv / hc:8.1f}")
print("\nActive today:", (dim_emp.employment_status == "Active").sum(), "| terminated:", (dim_emp.employment_status == "Terminated").sum())
