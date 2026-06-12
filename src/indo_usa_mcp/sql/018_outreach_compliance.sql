-- Anti-spam / CAN-SPAM compliance for outreach: an opt-out suppression list.
-- Any contact here is permanently excluded from outreach (honored opt-out / bounce /
-- complaint). Idempotent.

CREATE TABLE IF NOT EXISTS outreach_suppression (
    contact     TEXT        PRIMARY KEY,    -- normalized: lower(email) or phone digits only
    channel     TEXT,                       -- email / whatsapp / form (best-effort)
    reason      TEXT        NOT NULL DEFAULT 'optout'
                CHECK (reason IN ('optout', 'bounce', 'complaint', 'manual')),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
