PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS eval_datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS eval_cases (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    question TEXT NOT NULL,
    expected_answer TEXT,
    question_type TEXT NOT NULL,
    ambiguity_class TEXT NOT NULL CHECK (
        ambiguity_class IN (
            'clear',
            'context_resolvable',
            'genuinely_ambiguous'
        )
    ),
    answerability TEXT NOT NULL CHECK (
        answerability IN ('answerable', 'unanswerable')
    ),
    expected_behavior TEXT NOT NULL CHECK (
        expected_behavior IN (
            'answer', 'clarify', 'abstain'
        )
    ),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(dataset_id)
        REFERENCES eval_datasets(id)
);

CREATE TABLE IF NOT EXISTS eval_gold_evidence (
    case_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    requirement_group TEXT NOT NULL DEFAULT 'all',
    PRIMARY KEY(case_id, memory_id, requirement_group),
    FOREIGN KEY(case_id)
        REFERENCES eval_cases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    variant TEXT NOT NULL CHECK (
        variant IN (
            'baseline', 'pma_a', 'pma_b',
            'pma_c', 'pma'
        )
    ),
    commit_sha TEXT,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    environment_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'running',
            'completed', 'failed', 'cancelled'
        )
    ),
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    FOREIGN KEY(dataset_id)
        REFERENCES eval_datasets(id)
);

CREATE TABLE IF NOT EXISTS eval_case_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    actual_answer TEXT,
    response_behavior TEXT CHECK (
        response_behavior IN (
            'answer', 'clarify', 'abstain'
        )
    ),
    verdict TEXT NOT NULL CHECK (
        verdict IN (
            'pass', 'fail', 'pending_review',
            'not_applicable', 'error'
        )
    ),
    latency_ms REAL,
    error_type TEXT,
    retrieval_status TEXT,
    grounding_status TEXT,
    evaluation_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(run_id, case_id),
    FOREIGN KEY(run_id)
        REFERENCES eval_runs(id),
    FOREIGN KEY(case_id)
        REFERENCES eval_cases(id)
);

CREATE TABLE IF NOT EXISTS eval_metrics (
    run_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    numerator REAL,
    denominator REAL,
    value REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, metric_name),
    FOREIGN KEY(run_id)
        REFERENCES eval_runs(id)
);

CREATE TABLE IF NOT EXISTS eval_trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    event_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(result_id, event_index),
    FOREIGN KEY(result_id)
        REFERENCES eval_case_results(id)
);

CREATE TABLE IF NOT EXISTS eval_claims (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    support_status TEXT NOT NULL CHECK (
        support_status IN (
            'supported', 'unsupported', 'uncertain'
        )
    ),
    evidence_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(result_id)
        REFERENCES eval_case_results(id)
);

CREATE INDEX IF NOT EXISTS idx_eval_cases_dataset
    ON eval_cases(dataset_id);

CREATE INDEX IF NOT EXISTS idx_eval_results_run_verdict
    ON eval_case_results(run_id, verdict);

CREATE INDEX IF NOT EXISTS idx_eval_results_error
    ON eval_case_results(run_id, error_type);

CREATE INDEX IF NOT EXISTS idx_eval_trace_result
    ON eval_trace_events(result_id, event_index);

CREATE INDEX IF NOT EXISTS idx_eval_runs_dataset
    ON eval_runs(dataset_id, started_at);