-- Structured, grounded review signal beyond the numeric rating + prose summary: short customer-language
-- aspect tags ("great biryani", "long wait", "family friendly") + an overall sentiment label. Lets Dost
-- answer qualitative questions and lets these phrases feed semantic search. Populated by the LLM
-- enrichment agent from real review text only (never invented).
ALTER TABLE ai_content ADD COLUMN IF NOT EXISTS aspects   TEXT[];
ALTER TABLE ai_content ADD COLUMN IF NOT EXISTS sentiment TEXT;   -- positive | mixed | negative
