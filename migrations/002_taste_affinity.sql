-- Add anonymous taste tokens for collaborative filtering.
-- A taste_id is a random UUID generated client-side — no PII, no user identity.
-- It links one person's feedback entries so the algorithm can find taste-similar people.

ALTER TABLE feedback ADD COLUMN taste_id TEXT;

-- Partial indexes: only index rows that have a taste_id (most won't early on)
CREATE INDEX idx_feedback_taste_id ON feedback (taste_id) WHERE taste_id IS NOT NULL;
CREATE INDEX idx_feedback_place_taste ON feedback (place_id, taste_id, sentiment) WHERE taste_id IS NOT NULL;
