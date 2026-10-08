-- HR demo model. Run with your DATABASE and SCHEMA already selected (the loader does this).
-- PK/FK constraints in Snowflake are informational (not enforced) but Tableau and BI tools use them.

CREATE OR REPLACE TABLE DIM_DEPARTMENT (
  department_id NUMBER(3,0) PRIMARY KEY,
  department_name VARCHAR(60) NOT NULL,
  cost_center VARCHAR(20),
  department_head_employee_id NUMBER(8,0)
) COMMENT = 'One row per department. Executive (id 9) holds the CEO.';

CREATE OR REPLACE TABLE DIM_JOB (
  job_id NUMBER(4,0) PRIMARY KEY,
  job_title VARCHAR(80) NOT NULL,
  job_level NUMBER(2,0) COMMENT '1=junior ... 4=team lead, 5=VP/head, 6=CEO',
  job_family VARCHAR(60),
  department_id NUMBER(3,0),
  salary_band_min NUMBER(10,0), salary_band_mid NUMBER(10,0), salary_band_max NUMBER(10,0)
) COMMENT = 'Job catalogue with current monthly ILS salary bands.';

CREATE OR REPLACE TABLE DIM_EMPLOYEE (
  employee_id NUMBER(8,0) PRIMARY KEY,
  first_name VARCHAR(50), last_name VARCHAR(50), gender VARCHAR(1),
  birth_date DATE, email VARCHAR(120), phone VARCHAR(20), city VARCHAR(50), office_location VARCHAR(50),
  hire_date DATE NOT NULL,
  termination_date DATE COMMENT 'NULL while employed',
  termination_type VARCHAR(20) COMMENT 'Resignation | Involuntary',
  exit_reason VARCHAR(50),
  employment_status VARCHAR(12) COMMENT 'Active | Terminated',
  department_id NUMBER(3,0) COMMENT 'current (or last) department',
  job_id NUMBER(4,0) COMMENT 'current (or last) job',
  manager_id NUMBER(8,0),
  monthly_salary NUMBER(10,0) COMMENT 'ILS per month, current or last',
  performance_rating NUMBER(1,0) COMMENT '1 (low) - 5 (high)'
) COMMENT = 'One row per person ever employed (active + leavers).';

CREATE OR REPLACE TABLE FACT_LIFECYCLE_EVENT (
  event_id NUMBER(10,0) PRIMARY KEY,
  employee_id NUMBER(8,0),
  event_type VARCHAR(30) COMMENT 'Hire | Promotion | Salary Adjustment | Department Transfer | Termination',
  event_date DATE,
  from_department_id NUMBER(3,0), to_department_id NUMBER(3,0),
  from_job_id NUMBER(4,0), to_job_id NUMBER(4,0),
  old_monthly_salary NUMBER(10,0), new_monthly_salary NUMBER(10,0),
  reason VARCHAR(100)
) COMMENT = 'Career history events.';

CREATE OR REPLACE TABLE FACT_ABSENCE (
  absence_id NUMBER(10,0) PRIMARY KEY,
  employee_id NUMBER(8,0),
  leave_type VARCHAR(20) COMMENT 'Vacation | Sick Leave | Unpaid Leave',
  start_date DATE, end_date DATE,
  working_days NUMBER(4,0) COMMENT 'Sun-Thu working days covered'
) COMMENT = 'Leave blocks 2022-01 onward.';

CREATE OR REPLACE TABLE FACT_ATTENDANCE (
  attendance_id NUMBER(12,0) PRIMARY KEY,
  employee_id NUMBER(8,0),
  department_id NUMBER(3,0) COMMENT 'department on that date',
  work_date DATE,
  clock_in_ts TIMESTAMP_NTZ,
  clock_out_ts TIMESTAMP_NTZ COMMENT 'NULL = missing clock-out',
  hours_worked NUMBER(5,2) COMMENT 'net of 30 min break',
  overtime_hours NUMBER(5,2) COMMENT 'hours beyond 8, only counted when >= 0.5'
) COMMENT = 'Daily clock logs 2024-01 onward. Standard week Sun-Thu.';

CREATE OR REPLACE TABLE FACT_EMPLOYEE_MONTHLY_SNAPSHOT (
  snapshot_month_end DATE,
  employee_id NUMBER(8,0),
  department_id NUMBER(3,0),
  job_id NUMBER(4,0),
  monthly_salary NUMBER(10,0),
  tenure_months NUMBER(6,1),
  months_since_last_promotion NUMBER(6,1),
  is_active_eom NUMBER(1,0) COMMENT '1 = employed at month end',
  hired_in_month NUMBER(1,0),
  terminated_in_month NUMBER(1,0),
  PRIMARY KEY (snapshot_month_end, employee_id)
) COMMENT = 'Month-end headcount snapshot 2019-01 onward. Turnover % = SUM(terminated_in_month) / AVG monthly headcount.';

CREATE OR REPLACE TABLE FACT_DEPARTMENT_BUDGET (
  budget_id NUMBER(6,0) PRIMARY KEY,
  fiscal_year NUMBER(4,0),
  department_id NUMBER(3,0),
  budgeted_headcount NUMBER(5,0),
  annual_budget_ils NUMBER(14,0)
) COMMENT = 'Annual people budget per department.';


-- Foreign keys (informational in Snowflake; they document the model for BI tools)
ALTER TABLE DIM_JOB ADD FOREIGN KEY (department_id) REFERENCES DIM_DEPARTMENT(department_id);
ALTER TABLE DIM_EMPLOYEE ADD FOREIGN KEY (department_id) REFERENCES DIM_DEPARTMENT(department_id);
ALTER TABLE DIM_EMPLOYEE ADD FOREIGN KEY (job_id) REFERENCES DIM_JOB(job_id);
ALTER TABLE FACT_LIFECYCLE_EVENT ADD FOREIGN KEY (employee_id) REFERENCES DIM_EMPLOYEE(employee_id);
ALTER TABLE FACT_ABSENCE ADD FOREIGN KEY (employee_id) REFERENCES DIM_EMPLOYEE(employee_id);
ALTER TABLE FACT_ATTENDANCE ADD FOREIGN KEY (employee_id) REFERENCES DIM_EMPLOYEE(employee_id);
ALTER TABLE FACT_ATTENDANCE ADD FOREIGN KEY (department_id) REFERENCES DIM_DEPARTMENT(department_id);
ALTER TABLE FACT_EMPLOYEE_MONTHLY_SNAPSHOT ADD FOREIGN KEY (employee_id) REFERENCES DIM_EMPLOYEE(employee_id);
ALTER TABLE FACT_EMPLOYEE_MONTHLY_SNAPSHOT ADD FOREIGN KEY (department_id) REFERENCES DIM_DEPARTMENT(department_id);
ALTER TABLE FACT_EMPLOYEE_MONTHLY_SNAPSHOT ADD FOREIGN KEY (job_id) REFERENCES DIM_JOB(job_id);
ALTER TABLE FACT_DEPARTMENT_BUDGET ADD FOREIGN KEY (department_id) REFERENCES DIM_DEPARTMENT(department_id);
ALTER TABLE DIM_EMPLOYEE ADD FOREIGN KEY (manager_id) REFERENCES DIM_EMPLOYEE(employee_id);
