-- Search quality: keyword/dish tags for recall + filtering. Idempotent.

ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE temples     ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE groceries   ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_rest_tags ON restaurants USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_grocery_tags ON groceries USING gin (tags);
