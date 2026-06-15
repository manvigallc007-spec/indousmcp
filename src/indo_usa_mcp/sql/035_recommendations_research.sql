-- Phase-3 self-population: an optional free-LLM "research" note per recommendation — does this
-- unmet demand fit the Indians-from-India-in-USA mission, which category, and the best FREE source
-- to populate it. Advisory only; a human still approves at /admin/recommendations. Idempotent.

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS research      TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS researched_at TIMESTAMPTZ;
