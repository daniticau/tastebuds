-- Friends: one-to-one links between taste tokens, weighted by closeness.
-- The agent knows who a person messages most (Instagram, WhatsApp, iMessage).
-- It sends only a closeness level from 1 to 3. No names, numbers, or message counts reach this database.

-- One invite per friend. Single use. The code doubles as the agent's handle for that friend.
CREATE TABLE friend_invites (
    invite_code       TEXT PRIMARY KEY,
    inviter_taste_id  TEXT NOT NULL,
    inviter_closeness SMALLINT NOT NULL CHECK (inviter_closeness BETWEEN 1 AND 3),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ NOT NULL,
    accepted_at       TIMESTAMPTZ
);

CREATE INDEX idx_friend_invites_inviter ON friend_invites (inviter_taste_id);

-- One row per direction. taste_id is the person whose ranking the row shapes.
-- Each side sets its own closeness: A may text B daily while B rarely replies.
CREATE TABLE friend_ties (
    taste_id        TEXT NOT NULL,
    friend_taste_id TEXT NOT NULL,
    closeness       SMALLINT NOT NULL CHECK (closeness BETWEEN 1 AND 3),
    friend_ref      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (taste_id, friend_taste_id),
    CHECK (taste_id <> friend_taste_id)
);

CREATE UNIQUE INDEX idx_friend_ties_ref ON friend_ties (taste_id, friend_ref);
CREATE INDEX idx_friend_ties_friend ON friend_ties (friend_taste_id);
