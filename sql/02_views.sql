-- Analytical views (create after loading data). Data "as-of" date = last attendance date.

CREATE OR REPLACE VIEW V_ATTENDANCE_DAILY AS
SELECT a.attendance_id, a.employee_id, e.first_name || ' ' || e.last_name AS employee_name,
       a.department_id, d.department_name, a.work_date, DAYNAME(a.work_date) AS weekday,
       a.clock_in_ts, a.clock_out_ts, a.hours_worked, a.overtime_hours,
       HOUR(a.clock_in_ts) + MINUTE(a.clock_in_ts)/60 AS clock_in_hour,
       IFF(a.clock_out_ts IS NULL, 1, 0)                                   AS is_missing_clock_out,
       IFF(HOUR(a.clock_in_ts) * 60 + MINUTE(a.clock_in_ts) > 570, 1, 0)   AS is_late_arrival,      -- after 09:30
       IFF(COALESCE(a.overtime_hours,0) >= 2, 1, 0)                         AS is_excessive_overtime, -- 2h+ in a day
       IFF(DAYNAME(a.work_date) IN ('Fri','Sat'), 1, 0)                     AS is_weekend_work,
       IFF(a.hours_worked < 6, 1, 0)                                        AS is_short_day
FROM FACT_ATTENDANCE a
JOIN DIM_EMPLOYEE e   ON e.employee_id = a.employee_id
JOIN DIM_DEPARTMENT d ON d.department_id = a.department_id;

-- Working days (Sun-Thu) with neither a clock log nor an approved leave = "missing logs"
CREATE OR REPLACE VIEW V_MISSING_LOGS AS
WITH cal AS (
  SELECT DATEADD(day, SEQ4(), '2024-01-01'::DATE) AS d
  FROM TABLE(GENERATOR(ROWCOUNT => 1200))
), wd AS (
  SELECT d FROM cal
  WHERE d <= (SELECT MAX(work_date) FROM FACT_ATTENDANCE) AND DAYNAME(d) IN ('Sun','Mon','Tue','Wed','Thu')
)
SELECT e.employee_id, e.first_name || ' ' || e.last_name AS employee_name, e.department_id, dd.department_name, wd.d AS missing_date
FROM wd
JOIN DIM_EMPLOYEE e ON wd.d > e.hire_date AND wd.d < COALESCE(e.termination_date, '2999-12-31'::DATE)
JOIN DIM_DEPARTMENT dd ON dd.department_id = e.department_id
WHERE NOT EXISTS (SELECT 1 FROM FACT_ATTENDANCE a WHERE a.employee_id = e.employee_id AND a.work_date = wd.d)
  AND NOT EXISTS (SELECT 1 FROM FACT_ABSENCE b WHERE b.employee_id = e.employee_id AND wd.d BETWEEN b.start_date AND b.end_date);

-- One row per employee with tenure, pay position and a transparent attrition-risk score
CREATE OR REPLACE VIEW V_EMPLOYEE_360 AS
WITH as_of AS (SELECT MAX(work_date) AS d FROM FACT_ATTENDANCE),
ot AS (
  SELECT employee_id, AVG(COALESCE(overtime_hours,0)) AS avg_ot_hours_90d
  FROM FACT_ATTENDANCE, as_of WHERE work_date > DATEADD(day,-90,as_of.d) GROUP BY employee_id),
sick AS (
  SELECT employee_id, SUM(working_days) AS sick_days_90d
  FROM FACT_ABSENCE, as_of WHERE leave_type = 'Sick Leave' AND start_date > DATEADD(day,-90,as_of.d) GROUP BY employee_id),
promo AS (
  SELECT employee_id, MAX(event_date) AS last_promotion_date FROM FACT_LIFECYCLE_EVENT WHERE event_type IN ('Promotion','Hire') GROUP BY employee_id),
base AS (
  SELECT e.*, d.department_name, j.job_title, j.job_level, j.salary_band_mid,
         m.first_name || ' ' || m.last_name AS manager_name,
         DATEDIFF(day, e.hire_date, COALESCE(e.termination_date, as_of.d)) / 365.25 AS tenure_years,
         DATEDIFF(month, p.last_promotion_date, COALESCE(e.termination_date, as_of.d)) AS months_since_promotion,
         e.monthly_salary / NULLIF(j.salary_band_mid,0) AS compa_ratio,
         COALESCE(ot.avg_ot_hours_90d,0) AS avg_ot_hours_90d, COALESCE(sick.sick_days_90d,0) AS sick_days_90d
  FROM DIM_EMPLOYEE e
  JOIN DIM_DEPARTMENT d ON d.department_id = e.department_id
  JOIN DIM_JOB j ON j.job_id = e.job_id
  LEFT JOIN DIM_EMPLOYEE m ON m.employee_id = e.manager_id
  LEFT JOIN promo p ON p.employee_id = e.employee_id
  LEFT JOIN ot ON ot.employee_id = e.employee_id
  LEFT JOIN sick ON sick.employee_id = e.employee_id
  CROSS JOIN as_of)
SELECT base.*,
  CASE WHEN tenure_years < 1 THEN '<1 yr' WHEN tenure_years < 2 THEN '1-2 yrs' WHEN tenure_years < 3 THEN '2-3 yrs'
       WHEN tenure_years < 5 THEN '3-5 yrs' ELSE '5+ yrs' END AS tenure_band,
  IFF(employment_status = 'Active',
      25*IFF(compa_ratio < 0.92,1,0) + 20*IFF(job_level < 4 AND months_since_promotion > 30,1,0) + 15*IFF(tenure_years < 2,1,0)
      + 20*IFF(avg_ot_hours_90d > 1.0,1,0) + 20*IFF(sick_days_90d >= 3,1,0), NULL) AS risk_score,
  CASE WHEN employment_status <> 'Active' THEN NULL
       WHEN 25*IFF(compa_ratio < 0.92,1,0) + 20*IFF(job_level < 4 AND months_since_promotion > 30,1,0) + 15*IFF(tenure_years < 2,1,0)
            + 20*IFF(avg_ot_hours_90d > 1.0,1,0) + 20*IFF(sick_days_90d >= 3,1,0) >= 55 THEN 'High'
       WHEN 25*IFF(compa_ratio < 0.92,1,0) + 20*IFF(job_level < 4 AND months_since_promotion > 30,1,0) + 15*IFF(tenure_years < 2,1,0)
            + 20*IFF(avg_ot_hours_90d > 1.0,1,0) + 20*IFF(sick_days_90d >= 3,1,0) >= 30 THEN 'Medium'
       ELSE 'Low' END AS risk_band
FROM base;
