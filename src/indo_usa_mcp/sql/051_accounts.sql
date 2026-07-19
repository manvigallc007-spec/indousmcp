-- Consumer account layer. Shares the SAME login/session as business owners (session 'owner_email',
-- web/auth.py + users table). A profile row / saved places simply mark someone as a consumer -- there
-- is one account type, not a consumer/owner split. Powers the personalized "Today" feed, saved lists,
-- followed cities/categories, and digest notifications.

CREATE TABLE IF NOT EXISTS user_profiles (
    email              TEXT PRIMARY KEY,             -- lower-cased; FK-ish to users.email (not enforced,
                                                     -- so a magic-link/Google user with no users row still works)
    display_name       TEXT,
    home_city          TEXT,
    home_state         TEXT,                          -- 2-letter USPS code
    languages          TEXT[]  NOT NULL DEFAULT '{}',
    followed_verticals TEXT[]  NOT NULL DEFAULT '{}',
    notify_web         BOOLEAN NOT NULL DEFAULT FALSE,
    notify_email       BOOLEAN NOT NULL DEFAULT TRUE,
    digest_freq        TEXT    NOT NULL DEFAULT 'weekly',   -- off | daily | weekly
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saved_places (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT   NOT NULL,
    vertical    TEXT   NOT NULL,
    listing_id  BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (email, vertical, listing_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_places_email ON saved_places (email, created_at DESC);

CREATE TABLE IF NOT EXISTS follows (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL,
    kind        TEXT NOT NULL,                        -- 'city' | 'vertical'
    value       TEXT NOT NULL,                        -- e.g. 'Plano, TX' | 'restaurants'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (email, kind, value)
);
CREATE INDEX IF NOT EXISTS idx_follows_email ON follows (email);
