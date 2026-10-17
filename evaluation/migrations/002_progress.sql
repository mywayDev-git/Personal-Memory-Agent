CREATE TABLE IF NOT EXISTS eval_run_progress (
    run_id TEXT PRIMARY KEY REFERENCES eval_runs(id),
    case_id TEXT,
    stage TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
