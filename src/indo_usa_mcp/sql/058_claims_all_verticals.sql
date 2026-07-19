-- Generalize the claim system from restaurants-only to ALL verticals. Existing rows are restaurant
-- claims; back-fill record_id from restaurant_id and default vertical to 'restaurants'. restaurant_id
-- becomes nullable (non-restaurant claims leave it NULL and use (vertical, record_id)).
ALTER TABLE claims ADD COLUMN IF NOT EXISTS vertical  TEXT NOT NULL DEFAULT 'restaurants';
ALTER TABLE claims ADD COLUMN IF NOT EXISTS record_id BIGINT;
UPDATE claims SET record_id = restaurant_id WHERE record_id IS NULL;
ALTER TABLE claims ALTER COLUMN restaurant_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_claims_record ON claims (vertical, record_id);
CREATE INDEX IF NOT EXISTS idx_claims_owner  ON claims (owner_email) WHERE status = 'claimed';
