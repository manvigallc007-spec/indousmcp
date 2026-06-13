-- Stale-data lifecycle: mark which soft-deletes were AUTO-archived (unseen too long) vs
-- intentional admin/merge deletes — so auto-restore-on-re-sight never resurrects a merged
-- duplicate or an admin-removed listing. Idempotent.

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['restaurants','temples','groceries','professionals','salons',
                             'events','apparel','sweets','studios','services']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS auto_archived BOOLEAN NOT NULL DEFAULT false', t);
    END LOOP;
END $$;
