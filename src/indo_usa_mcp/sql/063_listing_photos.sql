-- Owner-uploaded listing photos.
--
-- Most listings have no picture: photo_url is only filled opportunistically by web-enrichment from
-- the business's own site, so a directory that otherwise reads well looks abandoned. This lets a
-- signed-in owner add real photos, moderated before they are public.
--
-- Derivatives, not originals: ingest re-encodes to WebP at up to three widths and keeps only those,
-- so there is no user-supplied file on disk to serve, and EXIF (which carries GPS) is dropped.

CREATE TABLE IF NOT EXISTS listing_photos (
    id              SERIAL PRIMARY KEY,
    vertical        TEXT        NOT NULL,
    listing_id      INTEGER     NOT NULL,
    owner_email     TEXT        NOT NULL,
    -- pending -> published | rejected ; removed = taken down by the owner afterwards
    status          TEXT        NOT NULL DEFAULT 'pending',
    -- relative paths under <upload_dir>/photos/, served by /uploads/photos/<file>
    path_sm         TEXT        NOT NULL,          -- 400w
    path_md         TEXT        NOT NULL,          -- 800w
    path_lg         TEXT,                          -- 1600w, only when the source was big enough
    width           INTEGER,                       -- of the largest derivative
    height          INTEGER,
    caption         TEXT,
    sort_order      INTEGER     NOT NULL DEFAULT 0,
    sha256          TEXT        NOT NULL,          -- same picture uploaded twice is rejected
    bytes_stored    INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    reviewed_by     TEXT,
    reject_reason   TEXT
);

-- The public read: published photos for one listing, in display order.
CREATE INDEX IF NOT EXISTS idx_listing_photos_listing
    ON listing_photos (vertical, listing_id, status, sort_order, id);

-- The admin queue.
CREATE INDEX IF NOT EXISTS idx_listing_photos_status
    ON listing_photos (status, created_at DESC);

-- An owner's own photos across their listings (portal + per-owner rate limit).
CREATE INDEX IF NOT EXISTS idx_listing_photos_owner
    ON listing_photos (lower(owner_email), created_at DESC);

-- Re-uploading the identical file is a no-op rather than a duplicate card in the gallery.
CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_photos_dedupe
    ON listing_photos (vertical, listing_id, sha256);
