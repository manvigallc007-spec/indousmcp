-- Tracks each flyer image a signed-in user uploads (portal or chat), independent of which approval
-- queue (submissions vs events) it ends up in. Lets /portal/flyer show "your past uploads" + status,
-- and keeps the extraction result + image around even if the user never completes the review step.
CREATE TABLE IF NOT EXISTS flyer_uploads (
    id                  BIGSERIAL PRIMARY KEY,
    uploader_email      TEXT NOT NULL,
    image_path          TEXT NOT NULL,               -- relative path under settings.upload_dir
    mime_type           TEXT NOT NULL,
    vertical_guess      TEXT,                         -- one of verticals.VERTICALS or 'events'; null = unsure
    extracted           JSONB,                        -- raw vision-model extraction (fields + confidence)
    status              TEXT NOT NULL DEFAULT 'extracted',  -- extracted | submitted | discarded
    created_submission_id BIGINT,                      -- set if routed to submissions.submit()
    created_event_id      BIGINT,                       -- set if routed to events.submit_flyer_event()
    error               TEXT,                          -- extraction failure detail, if any (row still kept)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_flyer_uploads_uploader ON flyer_uploads (uploader_email, created_at DESC);
