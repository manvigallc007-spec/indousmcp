-- OSM verification: cross-check non-OSM listings (IRS/NPPES/submissions/Socrata/consulates) against
-- OpenStreetMap to confirm + enrich them. `osm_checked_at` is the batch cursor (set on every check,
-- found or not, so we cycle through); `osm_verified_at` is stamped only on a confirmed match. Reward-
-- only: a miss never removes anything. Idempotent.

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons','events',
                             'apparel','sweets','studios','services','community','legal','education',
                             'realestate','finance']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS osm_checked_at TIMESTAMPTZ', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS osm_verified_at TIMESTAMPTZ', t);
    END LOOP;
END $$;
