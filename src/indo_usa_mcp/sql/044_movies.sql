-- Indian movies currently in US theaters (free, via the TMDB API). Time-sensitive content refreshed
-- by the `movies` agent — not a geographic business listing, so it lives outside the vertical
-- registry. Per-theater showtimes aren't available free/legally; we link out to buy tickets.
CREATE TABLE IF NOT EXISTS movies (
    id              SERIAL PRIMARY KEY,
    tmdb_id         INTEGER     UNIQUE NOT NULL,
    title           TEXT        NOT NULL,
    original_title  TEXT,
    language        TEXT,                          -- e.g. Telugu, Hindi, Tamil
    poster_url      TEXT,
    overview        TEXT,
    release_date    DATE,
    genres          TEXT[],
    popularity      REAL        DEFAULT 0,
    ticket_url      TEXT,                          -- search link to buy tickets / find showtimes
    now_playing     BOOLEAN     NOT NULL DEFAULT true,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS movies_now_playing_idx ON movies (now_playing, popularity DESC);
