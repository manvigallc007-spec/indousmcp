-- Owner self-submitted listings — go to a moderation queue; admin approves -> live record.
-- (Agents own events; submissions are for business verticals only.) Idempotent.

CREATE TABLE IF NOT EXISTS submissions (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vertical          TEXT        NOT NULL,
    payload           JSONB       NOT NULL,    -- form fields fed to verticals.create_record
    contact_email     TEXT,
    note              TEXT,                    -- owner's free-text note (admin context)
    status            TEXT        NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'approved', 'rejected')),
    created_record_id BIGINT,                  -- the live listing id once approved
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_submissions_pending ON submissions (status) WHERE status = 'pending';
