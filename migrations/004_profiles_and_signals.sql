-- Taste profiles, richer feedback signals, circles, and follow-up tracking.
-- Everything stays anonymous: the only key for a person is the taste token.

-- What one anonymous person eats. The agent fills it from conversation.
CREATE TABLE taste_profiles (
    taste_id          TEXT PRIMARY KEY,
    platform          TEXT,
    home_city         TEXT,
    home_city_display TEXT,
    neighborhoods     TEXT[] NOT NULL DEFAULT '{}',
    dietary           TEXT[] NOT NULL DEFAULT '{}',
    allergies         TEXT[] NOT NULL DEFAULT '{}',
    liked_cuisines    TEXT[] NOT NULL DEFAULT '{}',
    disliked_cuisines TEXT[] NOT NULL DEFAULT '{}',
    vibes             TEXT[] NOT NULL DEFAULT '{}',
    budget            SMALLINT CHECK (budget BETWEEN 1 AND 4),
    spice_level       SMALLINT CHECK (spice_level BETWEEN 0 AND 3),
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Richer feedback. One person holds one active opinion per place:
-- a newer opinion supersedes the older row instead of stacking votes.
ALTER TABLE feedback
    ADD COLUMN dishes        JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN occasion      TEXT,
    ADD COLUMN price_level   SMALLINT CHECK (price_level BETWEEN 1 AND 4),
    ADD COLUMN vibe_tags     TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN dietary_tags  TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN source        TEXT NOT NULL DEFAULT 'conversation'
        CHECK (source IN ('conversation', 'onboarding')),
    ADD COLUMN platform      TEXT,
    ADD COLUMN superseded_at TIMESTAMPTZ;

-- Apply the one-opinion rule to old rows: keep the newest opinion per person per place.
UPDATE feedback f
SET superseded_at = now()
FROM (
    SELECT id,
        ROW_NUMBER() OVER (
            PARTITION BY taste_id, place_id
            ORDER BY created_at DESC, id
        ) AS row_num
    FROM feedback
    WHERE taste_id IS NOT NULL
) ranked
WHERE f.id = ranked.id
  AND ranked.row_num > 1;

-- Rebuild the place aggregates from the active opinions.
WITH place_aggregates AS (
    SELECT
        p.id,
        COUNT(f.id) FILTER (WHERE f.sentiment = 'positive')::INTEGER AS positive_count,
        COUNT(f.id) FILTER (WHERE f.sentiment = 'negative')::INTEGER AS negative_count,
        COUNT(f.id) FILTER (WHERE f.sentiment = 'neutral')::INTEGER AS neutral_count
    FROM places p
    LEFT JOIN feedback f ON f.place_id = p.id AND f.superseded_at IS NULL
    GROUP BY p.id
)
UPDATE places p
SET positive_count = agg.positive_count,
    negative_count = agg.negative_count,
    neutral_count = agg.neutral_count,
    avg_rating = CASE
        WHEN agg.positive_count + agg.negative_count + agg.neutral_count = 0 THEN NULL
        ELSE (agg.positive_count + 0.5 * agg.neutral_count)::REAL
            / (agg.positive_count + agg.negative_count + agg.neutral_count)
    END,
    updated_at = now()
FROM place_aggregates agg
WHERE p.id = agg.id;

CREATE INDEX idx_feedback_active_taste_place
    ON feedback (taste_id, place_id)
    WHERE taste_id IS NOT NULL AND superseded_at IS NULL;
CREATE INDEX idx_feedback_taste_created
    ON feedback (taste_id, created_at DESC)
    WHERE taste_id IS NOT NULL;

-- Where a place is and what it costs.
ALTER TABLE places
    ADD COLUMN address     TEXT,
    ADD COLUMN latitude    DOUBLE PRECISION,
    ADD COLUMN longitude   DOUBLE PRECISION,
    ADD COLUMN price_sum   INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN price_count INTEGER NOT NULL DEFAULT 0;

-- Crowd tags per place: occasions, vibes, and dietary fit.
CREATE TABLE place_tags (
    place_id      UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('occasion', 'vibe', 'dietary')),
    tag           TEXT NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (place_id, kind, tag)
);

-- Dish-level opinions: "the teriyaki was amazing but the rice was meh".
CREATE TABLE place_dishes (
    place_id          UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    dish_normalized   TEXT NOT NULL,
    display_name      TEXT NOT NULL,
    positive_count    INTEGER NOT NULL DEFAULT 0,
    negative_count    INTEGER NOT NULL DEFAULT 0,
    neutral_count     INTEGER NOT NULL DEFAULT 0,
    last_mentioned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (place_id, dish_normalized)
);

-- Circles: friend groups that share taste. Members are taste tokens only.
CREATE TABLE circles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invite_code TEXT NOT NULL UNIQUE,
    name        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE circle_members (
    circle_id UUID NOT NULL REFERENCES circles(id) ON DELETE CASCADE,
    taste_id  TEXT NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (circle_id, taste_id)
);

CREATE INDEX idx_circle_members_taste ON circle_members (taste_id);

-- What the engine recommended to whom, so the agent can ask "how was it?" later.
CREATE TABLE recommendation_events (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taste_id          TEXT NOT NULL,
    place_id          UUID NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    rank              SMALLINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    followup_asked_at TIMESTAMPTZ,
    resolved_at       TIMESTAMPTZ
);

CREATE INDEX idx_recommendation_events_open
    ON recommendation_events (taste_id, created_at DESC)
    WHERE resolved_at IS NULL;
