-- Business-owner accounts: email + password (salted PBKDF2 hash), email verification, and recorded
-- Terms acceptance. Passwordless magic-link + Google sign-in still work alongside this (no password
-- row for those). Login flips owner sessions exactly as before (session 'owner_email').
CREATE TABLE IF NOT EXISTS users (
    email             TEXT PRIMARY KEY,           -- lower-cased
    password_hash     TEXT,                        -- pbkdf2_sha256$rounds$salt$hash (null = no password)
    email_verified    BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at       TIMESTAMPTZ,
    terms_accepted_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at     TIMESTAMPTZ
);
