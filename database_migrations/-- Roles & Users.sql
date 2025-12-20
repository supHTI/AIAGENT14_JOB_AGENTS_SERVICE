-- Roles & Users
INSERT INTO
  roles (id, name)
VALUES
  (1, 'Admin'),
  (2, 'User');
INSERT INTO
  users (
    id,
    name,
    username,
    email,
    password_hash,
    role_id,
    created_at,
    enable
  )
VALUES
  (
    1,
    'Admin One',
    'admin',
    'admin@example.com',
    'hash',
    1,
    NOW(),
    1
  ),
  (
    2,
    'User One',
    'user',
    'user@example.com',
    'hash',
    2,
    NOW(),
    1
  );
-- Session for user 1 (used by JWT sub to validate)
INSERT INTO
  sessions (id, user_id, session_id, login_at, is_active)
VALUES
  (1, 1, 'sess-abc-1', NOW(), 1);
-- Company + Jobs
INSERT INTO
  companies (id, company_id, company_name, location, industry)
VALUES
  (1, 'COMP1', 'Acme Corp', 'Mumbai', 'Software');
-- Job 1: cooling_period = 10 (we'll treat as days or months depending on your choice)
INSERT INTO
  job_openings (
    id,
    job_id,
    company_id,
    title,
    location,
    deadline,
    job_type,
    openings,
    cooling_period,
    created_at,
    created_by
  )
VALUES
  (
    105,
    'JOB-105',
    1,
    'Backend Developer',
    'Mumbai',
    '2030-01-01',
    'FULL_TIME',
    2,
    10,
    NOW(),
    1
  );
-- Job 2: no cooling
INSERT INTO
  job_openings (
    id,
    job_id,
    company_id,
    title,
    location,
    deadline,
    job_type,
    openings,
    cooling_period,
    created_at,
    created_by
  )
VALUES
  (
    104,
    'JOB-104',
    1,
    'Frontend Dev',
    'Remote',
    '2030-01-01',
    'FULL_TIME',
    3,
    0,
    NOW(),
    1
  );
-- Candidates
INSERT INTO
  candidates (
    candidate_id,
    candidate_email,
    candidate_name,
    created_by,
    created_at
  )
VALUES
  ('CAND-1', 'c1@example.com', 'Alice', 1, NOW()),
  ('CAND-2', 'c2@example.com', 'Bob', 1, NOW()),
  ('CAND-3', 'c3@example.com', 'Carol', 1, NOW()),
  (
    'CAND-4',
    'c4@example.com',
    'DuplicateJoin',
    1,
    NOW()
  );
-- CandidateJobs (map to jobs)
INSERT INTO
  candidate_jobs (id, job_id, candidate_id, created_at, created_by)
VALUES
  (1000, 104, 'CAND-1', NOW(), 1),
  -- will be in-progress (joined 5 days ago)
  (1001, 104, 'CAND-2', NOW(), 1),
  -- completed (joined 20 days ago)
  (1002, 105, 'CAND-3', NOW(), 1),
  -- job with no cooling -> skipped
  (1003, 104, 'CAND-4', NOW(), 1);
-- will get 2 JOINED statuses to test uniqueness
  -- CandidateJobStatus
  -- CAND-1: joined 5 days ago (if cooling_period = 10 days -> remaining 5)
INSERT INTO
  candidate_job_status (
    id,
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    5000,
    1000,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 5 DAY)
  );
-- CAND-2: joined 20 days ago (cooling 10 -> expired -> will set cooling_period_closed)
INSERT INTO
  candidate_job_status (
    id,
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    5001,
    1001,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 20 DAY)
  );
-- CAND-3: job has cooling_period=0 -> should be skipped
INSERT INTO
  candidate_job_status (
    id,
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    5002,
    1002,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 2 DAY)
  );
-- CAND-4: two JOINED statuses -> uniqueness check should skip (joined_count != 1)
INSERT INTO
  candidate_job_status (
    id,
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    5003,
    1003,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 2 DAY)
  ),
  (
    5004,
    1003,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 1 DAY)
  );
-- Add 5 more roles
INSERT INTO
  roles (id, name)
VALUES
  (3, 'Manager'),
  (4, 'Recruiter'),
  (5, 'Guest'),
  (6, 'Contractor'),
  (7, 'Intern');
-- Add 5 more users
INSERT INTO
  users (
    id,
    name,
    username,
    email,
    password_hash,
    role_id,
    created_at,
    enable
  )
VALUES
  (
    3,
    'Manager One',
    'manager',
    'manager@example.com',
    'hash',
    3,
    NOW(),
    1
  ),
  (
    4,
    'Recruiter One',
    'recruit',
    'recruit@example.com',
    'hash',
    4,
    NOW(),
    1
  ),
  (
    5,
    'Guest One',
    'guest',
    'guest@example.com',
    'hash',
    5,
    NOW(),
    0
  ),
  (
    6,
    'Contractor One',
    'contractor',
    'contractor@example.com',
    'hash',
    6,
    NOW(),
    1
  ),
  (
    7,
    'Intern One',
    'intern',
    'intern@example.com',
    'hash',
    7,
    NOW(),
    1
  );
-- Add 5 more sessions
INSERT INTO
  sessions (id, user_id, session_id, login_at, is_active)
VALUES
  (2, 3, 'sess-mgr-2', NOW(), 1),
  (3, 4, 'sess-rec-3', NOW(), 1),
  (4, 5, 'sess-guest-4', NOW(), 0),
  (
    5,
    6,
    'sess-ctr-5',
    DATE_SUB(NOW(), INTERVAL 2 DAY),
    1
  ),
  (
    6,
    7,
    'sess-int-6',
    DATE_SUB(NOW(), INTERVAL 1 DAY),
    1
  );
-- Add 5 more companies
INSERT INTO
  companies (id, company_id, company_name, location, industry)
VALUES
  (
    2,
    'COMP2',
    'Globex Inc',
    'Bengaluru',
    'Consulting'
  ),
  (3, 'COMP3', 'Innotech', 'Pune', 'Software'),
  (
    4,
    'COMP4',
    'NextGen Solutions',
    'Delhi',
    'Finance'
  ),
  (5, 'COMP5', 'BlueSky', 'Chennai', 'Healthcare'),
  (6, 'COMP6', 'Orbit Labs', 'Remote', 'Aerospace');
-- Add 5 more job_openings
INSERT INTO
  job_openings (
    id,
    job_id,
    company_id,
    title,
    location,
    deadline,
    job_type,
    openings,
    cooling_period,
    created_at,
    created_by
  )
VALUES
  (
    106,
    'JOB-106',
    2,
    'Fullstack Engineer',
    'Bengaluru',
    '2030-01-01',
    'FULL_TIME',
    1,
    30,
    NOW(),
    1
  ),
  (
    107,
    'JOB-107',
    2,
    'Data Analyst',
    'Delhi',
    '2030-01-01',
    'PART_TIME',
    2,
    0,
    NOW(),
    1
  ),
  (
    108,
    'JOB-108',
    3,
    'DevOps Engineer',
    'Mumbai',
    '2030-01-01',
    'FULL_TIME',
    1,
    10,
    NOW(),
    1
  ),
  (
    109,
    'JOB-109',
    4,
    'QA Engineer',
    'Remote',
    '2030-01-01',
    'FULL_TIME',
    1,
    5,
    NOW(),
    1
  ),
  (
    110,
    'JOB-110',
    5,
    'Product Manager',
    'Bengaluru',
    '2030-01-01',
    'FULL_TIME',
    1,
    15,
    NOW(),
    1
  );
-- Add 5 more candidates
INSERT INTO
  candidates (
    candidate_id,
    candidate_email,
    candidate_name,
    created_by,
    created_at
  )
VALUES
  ('CAND-5', 'c5@example.com', 'Eve', 1, NOW()),
  ('CAND-6', 'c6@example.com', 'Frank', 1, NOW()),
  ('CAND-7', 'c7@example.com', 'Grace', 1, NOW()),
  ('CAND-8', 'c8@example.com', 'Heidi', 1, NOW()),
  ('CAND-9', 'c9@example.com', 'Ivan', 1, NOW());
-- Add 5 more candidate_jobs
INSERT INTO
  candidate_jobs (id, job_id, candidate_id, created_at, created_by)
VALUES
  (1004, 106, 'CAND-5', NOW(), 1),
  (1005, 107, 'CAND-6', NOW(), 1),
  (1006, 108, 'CAND-7', NOW(), 1),
  (1007, 109, 'CAND-8', NOW(), 1),
  (1008, 110, 'CAND-9', NOW(), 1);
-- Add 6 candidate_job_status rows to exercise cooling & uniqueness checks (one candidate with 2 JOINED rows)
INSERT INTO
  candidate_job_status (
    id,
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    5005,
    1004,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 10 DAY)
  ),
  -- JOB-106 cooling 30 -> in-progress
  (
    5006,
    1005,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 2 DAY)
  ),
  -- JOB-107 cooling 0 -> should be skipped
  (
    5007,
    1006,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 20 DAY)
  ),
  -- JOB-108 cooling 10 -> expired
  (
    5008,
    1007,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 3 DAY)
  ),
  -- JOB-109: first JOINED
  (
    5009,
    1007,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 1 DAY)
  ),
  -- JOB-109: second JOINED -> uniqueness check
  (
    5010,
    1008,
    'JOINED',
    NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 1 DAY)
  );
-- JOB-110 cooling 15 -> in-progress
  -- NEW JOBS (distinct cooling_periods)
INSERT INTO
  job_openings (
    job_id,
    company_id,
    title,
    location,
    deadline,
    job_type,
    openings,
    cooling_period,
    created_at,
    created_by
  )
VALUES
  (
    'JOB-111',
    1,
    'SRE',
    'Bengaluru',
    '2030-01-01',
    'FULL_TIME',
    2,
    7,
    NOW(),
    1
  ),
  -- 7 days cooling
  (
    'JOB-112',
    1,
    'Data Eng',
    'Mumbai',
    '2030-01-01',
    'FULL_TIME',
    1,
    30,
    NOW(),
    1
  ),
  -- 30 days
  (
    'JOB-113',
    1,
    'Intern Frontend',
    'Remote',
    '2030-01-01',
    'PART_TIME',
    1,
    0,
    NOW(),
    1
  ),
  -- no cooling
  (
    'JOB-114',
    1,
    'QA Lead',
    'Delhi',
    '2030-01-01',
    'FULL_TIME',
    1,
    10,
    NOW(),
    1
  );
-- 10 days
  -- NEW CANDIDATES
INSERT INTO
  candidates (
    candidate_id,
    candidate_email,
    candidate_name,
    created_by,
    created_at
  )
VALUES
  ('CAND-10', 'c10@example.com', 'Liam', 1, NOW()),
  ('CAND-11', 'c11@example.com', 'Maya', 1, NOW()),
  ('CAND-12', 'c12@example.com', 'Noah', 1, NOW()),
  ('CAND-13', 'c13@example.com', 'Olivia', 1, NOW()),
  ('CAND-14', 'c14@example.com', 'Amir', 1, NOW()),
  ('CAND-15', 'c15@example.com', 'Rina', 1, NOW()),
  ('CAND-16', 'c16@example.com', 'Sanjay', 1, NOW()),
  ('CAND-17', 'c17@example.com', 'Tara', 1, NOW()),
  ('CAND-18', 'c18@example.com', 'Victor', 1, NOW()),
  ('CAND-19', 'c19@example.com', 'Wendy', 1, NOW()),
  ('CAND-20', 'c20@example.com', 'Xavier', 1, NOW());
-- MAP CANDIDATES TO JOBS (candidate_jobs)
INSERT INTO
  candidate_jobs (job_id, candidate_id, created_at, created_by)
VALUES
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-111'
    ),
    'CAND-10',
    NOW(),
    1
  ),
  -- in-progress (7-day job)
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-111'
    ),
    'CAND-11',
    NOW(),
    1
  ),
  -- duplicate JOINED
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-112'
    ),
    'CAND-12',
    NOW(),
    1
  ),
  -- expired (30-day job)
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-113'
    ),
    'CAND-13',
    NOW(),
    1
  ),
  -- job with no cooling (skip)
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-114'
    ),
    'CAND-14',
    NOW(),
    1
  ),
  -- missing joined_at
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-114'
    ),
    'CAND-15',
    NOW(),
    1
  ),
  -- already closed
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-111'
    ),
    'CAND-16',
    NOW(),
    1
  ),
  -- will be in-progress
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-112'
    ),
    'CAND-17',
    NOW(),
    1
  ),
  -- expired
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-114'
    ),
    'CAND-18',
    NOW(),
    1
  ),
  -- in-progress
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-111'
    ),
    'CAND-19',
    NOW(),
    1
  ),
  -- in-progress
  (
    (
      SELECT
        id
      FROM
        job_openings
      WHERE
        job_id = 'JOB-112'
    ),
    'CAND-20',
    NOW(),
    1
  );
-- in-progress (30-day)
  -- JOINED STATUSES (varied scenarios)
  -- In-progress: joined recently (within cooling)
INSERT INTO
  candidate_job_status (
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-10'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 3 DAY)
  ),
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-16'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 2 DAY)
  ),
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-18'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 4 DAY)
  ),
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-19'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 1 DAY)
  ),
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-20'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 5 DAY)
  );
-- Duplicate JOINED (should be skipped by your uniqueness check)
INSERT INTO
  candidate_job_status (
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-11'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 4 DAY)
  ),
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-11'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 1 DAY)
  );
-- Expired (joined long ago -> remaining_days <= 0)
INSERT INTO
  candidate_job_status (
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-12'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 40 DAY)
  ),
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-17'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 35 DAY)
  );
-- No cooling job (should be skipped)
INSERT INTO
  candidate_job_status (
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-13'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 2 DAY)
  );
-- Missing joined_at (should be guarded)
INSERT INTO
  candidate_job_status (
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at
  )
VALUES
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-14'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    NULL
  );
-- Already closed (cooling_period_closed set)
INSERT INTO
  candidate_job_status (
    candidate_job_id,
    type,
    created_at,
    created_by,
    joined_at,
    cooling_period_closed
  )
VALUES
  (
    (
      SELECT
        id
      FROM
        candidate_jobs
      WHERE
        candidate_id = 'CAND-15'
      LIMIT
        1
    ), 'JOINED', NOW(),
    1,
    DATE_SUB(NOW(), INTERVAL 20 DAY),
    DATE_SUB(NOW(), INTERVAL 5 DAY)
  );