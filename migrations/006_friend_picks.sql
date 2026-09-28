-- Friends can see which places each other liked, and why, when the friend agrees.
-- The server still holds no names. It returns the friend_ref, and the person's
-- own agent turns that into a name from its private notes.

-- friend_ties row (taste_id = A, friend_taste_id = B) shapes A's picks with B's opinions.
-- friend_shares_picks is B's choice: may A see B's picks, marked as B's?
-- Links made before this change were promised "counts only", so they start as FALSE.
ALTER TABLE friend_ties ADD COLUMN friend_shares_picks BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE friend_ties ALTER COLUMN friend_shares_picks SET DEFAULT TRUE;

ALTER TABLE friend_invites ADD COLUMN inviter_shares_picks BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE friend_invites ALTER COLUMN inviter_shares_picks SET DEFAULT TRUE;

-- What the engine already told a person about friends' finds.
-- Each find is told once, and a nudge happens at most once per cooldown.
CREATE TABLE friend_find_events (
    taste_id TEXT NOT NULL,
    place_id UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    nudged   BOOLEAN NOT NULL DEFAULT FALSE,
    shown_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (taste_id, place_id)
);

CREATE INDEX idx_friend_find_events_nudges
    ON friend_find_events (taste_id, shown_at DESC)
    WHERE nudged;
