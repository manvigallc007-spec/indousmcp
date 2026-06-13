-- Broken-link detection: track website check results so a dead URL is only removed after it
-- fails twice (never on a single transient blip). Idempotent.

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons',
                             'events','apparel','sweets','studios','services']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS link_strikes INT NOT NULL DEFAULT 0', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS link_checked_at TIMESTAMPTZ', t);
    END LOOP;
END $$;
