-- Community reviews: visitor-submitted star ratings + text reviews, moderated.
-- Clean reviews are auto-published; spam/abusive ones are held ('pending') and escalated to an
-- admin. The rolled-up community score lives in SEPARATE columns (community_rating*) so it never
-- clobbers the web-harvested `rating` (set by web_enrich.py from each business's own website).

CREATE TABLE IF NOT EXISTS reviews (
    id            BIGSERIAL PRIMARY KEY,
    vertical      TEXT     NOT NULL,                 -- e.g. 'restaurants' (== listing table name)
    listing_id    BIGINT   NOT NULL,                 -- id in that vertical's table
    rating        SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title         TEXT,
    body          TEXT,
    author_name   TEXT,                              -- optional; "Anonymous" if blank
    author_email  TEXT,                              -- optional; NEVER exposed publicly
    status        TEXT     NOT NULL DEFAULT 'pending', -- 'published' | 'pending' | 'rejected'
    flagged_reason TEXT,                             -- why it was held (spam/links/profanity/...)
    ip            TEXT,                              -- for abuse detection / per-IP dedupe
    source        TEXT     NOT NULL DEFAULT 'web',   -- 'web' | 'agent' | 'api'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    moderated_at  TIMESTAMPTZ,
    moderated_by  TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_listing ON reviews (vertical, listing_id, status);
CREATE INDEX IF NOT EXISTS idx_reviews_status  ON reviews (status);
CREATE INDEX IF NOT EXISTS idx_reviews_created ON reviews (created_at DESC);

-- Community rating roll-up columns on every listing table (separate from web-harvested rating).
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons','events',
                             'apparel','sweets','studios','services','community','legal','education',
                             'realestate','finance']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS community_rating REAL', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS community_rating_count INT', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS community_rating_updated_at TIMESTAMPTZ', t);
    END LOOP;
END $$;
