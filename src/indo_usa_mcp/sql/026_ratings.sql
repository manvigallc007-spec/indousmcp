-- Ratings as a trust signal: ensure EVERY vertical has the website-enrichment columns, so the
-- 4 newer verticals (apparel/sweets/studios/services) can also carry harvested ratings/photo/
-- socials. The 6 original verticals already have these (migration 017) — IF NOT EXISTS = no-op.

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons',
                             'events','apparel','sweets','studios','services']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS rating REAL', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS rating_count INT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS photo_url TEXT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS socials JSONB', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS web_enriched_at TIMESTAMPTZ', t);
    END LOOP;
END $$;
