-- Search quality: natural-language description per record (better for LLM agents +
-- embeddings). Idempotent.

ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE temples     ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE groceries   ADD COLUMN IF NOT EXISTS description TEXT;
