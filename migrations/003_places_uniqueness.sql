-- Merge duplicate normalized places, then enforce uniqueness at the database level.

WITH ranked_places AS (
    SELECT
        id,
        city,
        name_normalized,
        created_at,
        FIRST_VALUE(id) OVER (
            PARTITION BY city, name_normalized
            ORDER BY created_at, id
        ) AS canonical_id,
        ROW_NUMBER() OVER (
            PARTITION BY city, name_normalized
            ORDER BY created_at, id
        ) AS row_num
    FROM places
),
duplicate_places AS (
    SELECT
        id AS duplicate_id,
        canonical_id
    FROM ranked_places
    WHERE row_num > 1
)
UPDATE feedback f
SET place_id = dp.canonical_id
FROM duplicate_places dp
WHERE f.place_id = dp.duplicate_id;

WITH ranked_places AS (
    SELECT
        id,
        city,
        name_normalized,
        neighborhood,
        cuisine_tags,
        created_at,
        FIRST_VALUE(id) OVER (
            PARTITION BY city, name_normalized
            ORDER BY created_at, id
        ) AS canonical_id
    FROM places
),
canonical_places AS (
    SELECT DISTINCT canonical_id
    FROM ranked_places
),
merged_place_data AS (
    SELECT
        cp.canonical_id,
        (
            SELECT rp.neighborhood
            FROM ranked_places rp
            WHERE rp.canonical_id = cp.canonical_id
              AND rp.neighborhood IS NOT NULL
            ORDER BY (rp.id <> cp.canonical_id), rp.created_at, rp.id
            LIMIT 1
        ) AS merged_neighborhood,
        COALESCE(
            ARRAY(
                SELECT DISTINCT tag
                FROM ranked_places rp
                CROSS JOIN LATERAL unnest(
                    COALESCE(rp.cuisine_tags, ARRAY[]::TEXT[])
                ) AS cuisine_tag(tag)
                WHERE rp.canonical_id = cp.canonical_id
                ORDER BY tag
            ),
            ARRAY[]::TEXT[]
        ) AS merged_cuisine_tags
    FROM canonical_places cp
)
UPDATE places p
SET neighborhood = COALESCE(p.neighborhood, mpd.merged_neighborhood),
    cuisine_tags = mpd.merged_cuisine_tags,
    updated_at = now()
FROM merged_place_data mpd
WHERE p.id = mpd.canonical_id;

WITH ranked_places AS (
    SELECT
        id,
        city,
        name_normalized,
        FIRST_VALUE(id) OVER (
            PARTITION BY city, name_normalized
            ORDER BY created_at, id
        ) AS canonical_id,
        ROW_NUMBER() OVER (
            PARTITION BY city, name_normalized
            ORDER BY created_at, id
        ) AS row_num
    FROM places
)
DELETE FROM places p
USING ranked_places rp
WHERE p.id = rp.id
  AND rp.row_num > 1;

WITH place_aggregates AS (
    SELECT
        p.id,
        COUNT(f.id) FILTER (WHERE f.sentiment = 'positive')::INTEGER AS positive_count,
        COUNT(f.id) FILTER (WHERE f.sentiment = 'negative')::INTEGER AS negative_count,
        COUNT(f.id) FILTER (WHERE f.sentiment = 'neutral')::INTEGER AS neutral_count,
        CASE
            WHEN COUNT(f.id) = 0 THEN NULL
            ELSE (
                COUNT(f.id) FILTER (WHERE f.sentiment = 'positive')
                + 0.5 * COUNT(f.id) FILTER (WHERE f.sentiment = 'neutral')
            )::REAL / COUNT(f.id)
        END AS avg_rating,
        MAX(f.created_at) AS last_feedback_at
    FROM places p
    LEFT JOIN feedback f ON f.place_id = p.id
    GROUP BY p.id
)
UPDATE places p
SET positive_count = agg.positive_count,
    negative_count = agg.negative_count,
    neutral_count = agg.neutral_count,
    avg_rating = agg.avg_rating,
    last_feedback_at = agg.last_feedback_at,
    updated_at = now()
FROM place_aggregates agg
WHERE p.id = agg.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_places_city_name_normalized_unique
    ON places (city, name_normalized);
