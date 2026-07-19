-- Referral loop: each member gets a stable share code; a new member who joins via someone's invite
-- link is attributed to that referrer. Powers the "invite friends" growth loop + a count on /me.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS referral_code TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS referred_by   TEXT;   -- the referrer's email
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_refcode ON user_profiles (referral_code)
    WHERE referral_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_profiles_referredby ON user_profiles (referred_by)
    WHERE referred_by IS NOT NULL;
