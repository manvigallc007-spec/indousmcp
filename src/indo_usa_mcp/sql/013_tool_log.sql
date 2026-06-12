-- Agent traffic analytics: one row per MCP tool call. Idempotent.

CREATE TABLE IF NOT EXISTS tool_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tool         TEXT        NOT NULL,
    client       TEXT,                    -- MCP client/agent (name/version) when provided
    args         JSONB,                   -- the call's arguments (small)
    result_count INT,                     -- number of records returned, when applicable
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_log_time ON tool_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_log_tool ON tool_log (tool, created_at DESC);
