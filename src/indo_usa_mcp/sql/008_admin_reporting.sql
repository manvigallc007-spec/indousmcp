-- Admin reporting: one snapshot row per day (health + growth metrics). Idempotent.

CREATE TABLE IF NOT EXISTS daily_reports (
    report_date DATE        PRIMARY KEY,
    metrics     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
