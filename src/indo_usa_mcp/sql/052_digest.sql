-- Tracks when a consumer last received their "Today in Indian America" email digest, so the digest
-- agent can honor per-user cadence (daily/weekly) idempotently.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS digest_sent_at TIMESTAMPTZ;
