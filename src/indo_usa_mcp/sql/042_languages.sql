-- Languages spoken at a listing (e.g. {Telugu, Hindi, English}) — the diaspora moat: answers
-- "Telugu-speaking gynecologist" queries that generic platforms can't. Owner/admin-provided (no
-- free source, no inference), so it starts empty and grows via claims/submissions. Folded into the
-- searchable tags[] ("telugu-speaking") + the embedded description, so search needs no new filter.

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons','events',
                             'apparel','sweets','studios','services','community','legal','education',
                             'realestate','finance']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS languages TEXT[]', t);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I USING GIN (languages)',
                       'idx_' || t || '_languages', t);
    END LOOP;
END $$;
