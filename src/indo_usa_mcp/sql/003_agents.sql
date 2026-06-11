-- Autonomous agent layer (blueprint §6). Idempotent.

-- ---------------------------------------------------------------------------
-- One row per agent execution: what ran, how long, outcome, structured result.
-- This is the audit trail the Monitoring Agent reads to detect failures.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent       TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','success','error')),
    params      JSONB,
    result      JSONB,
    error       TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    duration_ms INT
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs (agent, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_errors ON agent_runs (started_at DESC)
    WHERE status = 'error';

-- ---------------------------------------------------------------------------
-- Alerts raised by the Monitoring Agent (anomalies, scraper failures, backlogs).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_alerts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    severity    TEXT        NOT NULL DEFAULT 'warning'
                CHECK (severity IN ('info','warning','critical')),
    kind        TEXT        NOT NULL,
    message     TEXT        NOT NULL,
    details     JSONB,
    resolved    BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON agent_alerts (created_at DESC) WHERE NOT resolved;
