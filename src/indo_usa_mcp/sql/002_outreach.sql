-- Outreach & claiming system (blueprint §7). Idempotent.

-- ---------------------------------------------------------------------------
-- A claim attempt for a restaurant: a single-use token + verification state.
-- Owner verifies via email/phone, then gains the ability to update the profile.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claims (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id BIGINT      NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    token         TEXT        NOT NULL UNIQUE,        -- single-use secret in the claim link
    channel       TEXT        CHECK (channel IN ('email','whatsapp','instagram','form')),
    contact_target TEXT,                              -- the address/number contacted
    status        TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','sent','verified','claimed','expired','revoked')),
    owner_email   TEXT,
    owner_phone   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '30 days',
    verified_at   TIMESTAMPTZ,
    claimed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_claims_restaurant ON claims (restaurant_id);
CREATE INDEX IF NOT EXISTS idx_claims_open ON claims (status)
    WHERE status IN ('pending','sent','verified');

-- ---------------------------------------------------------------------------
-- Every outreach touch, for anti-spam cooldowns, auditing and reply tracking.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outreach_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id BIGINT      NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    claim_id      BIGINT      REFERENCES claims(id) ON DELETE SET NULL,
    channel       TEXT        NOT NULL,
    contact_target TEXT,
    message       TEXT,
    status        TEXT        NOT NULL DEFAULT 'drafted'
                  CHECK (status IN ('drafted','sent','failed','replied','bounced')),
    requires_human BOOLEAN    NOT NULL DEFAULT false,  -- chains / high-value / featured
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outreach_restaurant ON outreach_log (restaurant_id, created_at DESC);
