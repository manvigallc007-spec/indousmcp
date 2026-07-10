-- Pay-for-premium during onboarding, WITHOUT bypassing the approval gate: payment stamps these on
-- the submission; the featured placement is applied only at approval time (submissions.approve).
-- stripe_session_id lets an admin find the charge to refund a paid-but-rejected submission. Idempotent.
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS paid_featured_days INTEGER;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS stripe_session_id TEXT;
CREATE INDEX IF NOT EXISTS submissions_paid_unresolved_idx ON submissions (status)
    WHERE paid_featured_days IS NOT NULL AND status <> 'approved';
