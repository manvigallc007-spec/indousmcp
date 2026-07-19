-- Business-flywheel: give claimed-listing owners real engagement tools.
--  * owner_posts: offers/promos/announcements an owner posts on their own listing (shown on the
--    listing page + eligible for the Today feed). Time-boxed via expires_at.
--  * reviews.owner_reply: a public owner response under a community review (the owner's right of reply).

CREATE TABLE IF NOT EXISTS owner_posts (
    id           BIGSERIAL PRIMARY KEY,
    vertical     TEXT   NOT NULL,
    listing_id   BIGINT NOT NULL,
    owner_email  TEXT   NOT NULL,
    kind         TEXT   NOT NULL DEFAULT 'offer',     -- offer | announcement
    title        TEXT   NOT NULL,
    body         TEXT,
    expires_at   TIMESTAMPTZ,                          -- null = no expiry
    status       TEXT   NOT NULL DEFAULT 'active',     -- active | removed
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_owner_posts_listing
    ON owner_posts (vertical, listing_id) WHERE status = 'active';

ALTER TABLE reviews ADD COLUMN IF NOT EXISTS owner_reply    TEXT;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS owner_reply_at TIMESTAMPTZ;
