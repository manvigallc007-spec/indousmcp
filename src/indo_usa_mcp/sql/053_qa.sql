-- Ask-the-community Q&A. Members ask questions ("Telugu-speaking pediatrician in Plano?"); Dost posts
-- an instant AI answer, and the community adds + upvotes answers. Each question is a public, indexable
-- page (QAPage JSON-LD) -- a daily-fresh, SEO-friendly conversation surface. Content is screened with
-- the same moderation as reviews (clean auto-publishes; flagged waits).

CREATE TABLE IF NOT EXISTS questions (
    id             BIGSERIAL PRIMARY KEY,
    slug           TEXT UNIQUE,
    title          TEXT NOT NULL,
    body           TEXT,
    asker_email    TEXT,
    city           TEXT,
    state          TEXT,
    vertical       TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',      -- pending | published | rejected
    flagged_reason TEXT,
    view_count     INT  NOT NULL DEFAULT 0,
    answer_count   INT  NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_questions_published ON questions (created_at DESC) WHERE status = 'published';

CREATE TABLE IF NOT EXISTS answers (
    id           BIGSERIAL PRIMARY KEY,
    question_id  BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    body         TEXT   NOT NULL,
    author_email TEXT,                                    -- null for Dost's AI answer
    is_ai        BOOLEAN NOT NULL DEFAULT FALSE,
    status       TEXT   NOT NULL DEFAULT 'published',     -- pending | published | rejected
    upvotes      INT    NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_answers_question ON answers (question_id, created_at);

CREATE TABLE IF NOT EXISTS answer_votes (
    id         BIGSERIAL PRIMARY KEY,
    answer_id  BIGINT NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
    email      TEXT   NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (answer_id, email)
);
