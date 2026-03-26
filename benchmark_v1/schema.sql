PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY,
  subset TEXT NOT NULL,
  question_text TEXT NOT NULL,
  expected_type TEXT,
  question_version TEXT NOT NULL DEFAULT 'v1',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  run_name TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  temperature REAL NOT NULL,
  top_p REAL,
  max_tokens INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_family TEXT,
  api_base TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(provider, model_name)
);

CREATE TABLE IF NOT EXISTS responses (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL,
  run_id INTEGER NOT NULL,
  model_id INTEGER NOT NULL,
  prompt_text TEXT NOT NULL,
  raw_answer TEXT,
  normalized_answer TEXT,
  refused INTEGER NOT NULL DEFAULT 0,
  error INTEGER NOT NULL DEFAULT 0,
  error_type TEXT,
  error_message TEXT,
  latency_ms INTEGER,
  input_tokens INTEGER,
  output_tokens INTEGER,
  finish_reason TEXT,
  requested_model TEXT,
  returned_model TEXT,
  raw_request_path TEXT,
  raw_response_path TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(question_id) REFERENCES questions(id),
  FOREIGN KEY(run_id) REFERENCES runs(id),
  FOREIGN KEY(model_id) REFERENCES models(id)
);

CREATE TABLE IF NOT EXISTS question_metrics (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL,
  run_id INTEGER NOT NULL,
  answer_count INTEGER,
  refusal_rate REAL,
  mean_answer_length REAL,
  length_stddev REAL,
  divergence_score REAL,
  deep_dive_priority REAL,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(question_id) REFERENCES questions(id),
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_questions_subset ON questions(subset);
CREATE INDEX IF NOT EXISTS idx_responses_question_run ON responses(question_id, run_id);
CREATE INDEX IF NOT EXISTS idx_responses_model_run ON responses(model_id, run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_run_score ON question_metrics(run_id, divergence_score DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_response_once ON responses(question_id, run_id, model_id);
