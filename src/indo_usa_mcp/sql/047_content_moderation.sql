-- Admin moderation (pause / soft-delete) for the three content tables that today have zero admin
-- management: movies, h1b_sponsors, kb_documents. These aren't in verticals.VERTICALS, so they get
-- their own is_active/deleted_at columns rather than joining the registry. Same reversible
-- soft-delete convention as every vertical table (deleted_at = now()/NULL never hard-deletes).
ALTER TABLE movies       ADD COLUMN IF NOT EXISTS is_active  BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE movies       ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE h1b_sponsors ADD COLUMN IF NOT EXISTS is_active  BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE h1b_sponsors ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS is_active  BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS movies_active_idx       ON movies       (is_active) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS h1b_sponsors_active_idx ON h1b_sponsors (is_active) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS kb_documents_active_idx ON kb_documents (is_active) WHERE deleted_at IS NULL;
