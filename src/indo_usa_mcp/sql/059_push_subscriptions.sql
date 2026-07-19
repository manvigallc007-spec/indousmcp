-- Web push subscriptions (Push API). One row per browser/device endpoint a member opted in from; the
-- p256dh + auth keys are needed to encrypt the payload. Tied to the member's email so the digest agent
-- can push their personalized "Today" nudge. Dead endpoints are pruned on a 404/410 from the push service.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT NOT NULL,
    endpoint   TEXT NOT NULL UNIQUE,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_push_subs_email ON push_subscriptions (email);
