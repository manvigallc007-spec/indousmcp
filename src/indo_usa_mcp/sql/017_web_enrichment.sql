-- Website enrichment: structured signals read from each listing's OWN website
-- (schema.org JSON-LD + Open Graph + social links) — rating, price, photo, socials,
-- email/phone. Added to every vertical. Idempotent (safe to re-run).

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons','events']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS email TEXT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS menu_url TEXT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS price_range TEXT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS rating REAL', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS rating_count INT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS photo_url TEXT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS socials JSONB', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS web_enriched_at TIMESTAMPTZ', t);
    END LOOP;
END $$;
