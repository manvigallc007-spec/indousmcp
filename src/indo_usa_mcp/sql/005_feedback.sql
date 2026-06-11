-- Feedback / corrections queue (blueprint agent #5). Idempotent.
-- Agents or users propose field corrections; the Feedback agent applies safe ones.

CREATE TABLE IF NOT EXISTS feedback (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id  BIGINT      NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    field          TEXT        NOT NULL,
    proposed_value TEXT,
    reason         TEXT,
    source         TEXT        NOT NULL DEFAULT 'agent',
    status         TEXT        NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'applied', 'rejected', 'needs_review')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_feedback_pending ON feedback (status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_feedback_restaurant ON feedback (restaurant_id);
