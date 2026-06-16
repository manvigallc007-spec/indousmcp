-- Contact-form inbox: the ONLY inbound channel (no public email address on the site). An agent
-- drafts a reply per message; an admin reviews/edits/approves before anything is sent.
CREATE TABLE IF NOT EXISTS contact_messages (
    id            SERIAL PRIMARY KEY,
    name          TEXT,
    email         TEXT,                          -- the sender's email (so we can reply), never shown publicly
    subject       TEXT,
    body          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'new',   -- new | drafted | replied | closed
    draft_reply   TEXT,                          -- AI-drafted reply, awaiting human approval
    reply_sent_at TIMESTAMPTZ,
    ip            TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contact_messages_status ON contact_messages (status, created_at DESC);
