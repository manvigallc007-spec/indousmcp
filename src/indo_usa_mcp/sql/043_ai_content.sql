-- LLM-polished, grounded editorial content per listing, kept in a SIDE table so the templated
-- describe() output in each vertical's `description` column is never clobbered (and vice-versa).
-- One row per (vertical, listing_id). source_hash lets the enricher skip unchanged inputs.
CREATE TABLE IF NOT EXISTS ai_content (
    vertical        TEXT        NOT NULL,
    listing_id      INTEGER     NOT NULL,
    description     TEXT,                       -- natural-language rewrite of the known facts
    review_summary  TEXT,                       -- 1-sentence "what people say", grounded in reviews
    source_hash     TEXT,                       -- hash of the inputs; unchanged => skip re-generating
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (vertical, listing_id)
);
