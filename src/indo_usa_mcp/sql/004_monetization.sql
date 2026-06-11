-- Monetization (featured listings) + outreach delivery (email). Idempotent.

-- Paid "featured" window: a listing is effectively featured while is_featured is true
-- AND featured_until is null (permanent) or still in the future.
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS featured_until TIMESTAMPTZ;

-- Business contact email (from public sources), used by the Outreach Agent for delivery.
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS email TEXT;

CREATE INDEX IF NOT EXISTS idx_rest_featured_until ON restaurants (featured_until)
    WHERE featured_until IS NOT NULL;
