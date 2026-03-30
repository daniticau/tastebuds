from uuid import UUID

from tastebuds.config import get_settings
from tastebuds.db.client import get_pool
from tastebuds.db.models import (
    FeedbackResult,
    PlaceRecommendation,
    SearchResult,
    TrendingResult,
)
from tastebuds.normalizer import normalize_city, normalize_name

_SECONDS_PER_DAY = 86400


def compute_sentiment_summary(positive_pct: float, total: int) -> str:
    """Return a human-readable sentiment summary."""
    if total == 0:
        return "No reviews yet"
    if positive_pct >= 0.8 and total >= 3:
        return "Highly recommended"
    if positive_pct >= 0.6:
        return "Generally positive"
    if positive_pct >= 0.4:
        return "Mixed reviews"
    return "Not well received"


def _count_reviews(row: dict) -> int:
    """Count total reviews represented in an aggregated places row."""
    return row["positive_count"] + row["negative_count"] + row["neutral_count"]


def _build_place_recommendation(row: dict) -> PlaceRecommendation:
    """Convert a database row into the public recommendation shape."""
    total_reviews = _count_reviews(row)
    positive_pct = row["positive_count"] / max(total_reviews, 1)

    return PlaceRecommendation(
        name=row["canonical_name"],
        city=row["city"],
        neighborhood=row["neighborhood"],
        cuisine_tags=row["cuisine_tags"],
        sentiment_summary=compute_sentiment_summary(positive_pct, total_reviews),
        positive_pct=round(positive_pct, 2),
        total_reviews=total_reviews,
        last_reviewed=(
            row["last_feedback_at"].isoformat()
            if row["last_feedback_at"]
            else None
        ),
    )


def _build_ilike_contains_pattern(value: str | None) -> str | None:
    """Build a safely escaped substring pattern for ILIKE."""
    if value is None:
        return None

    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _build_search_message(
    recommendations: list[PlaceRecommendation],
    city: str,
    cuisine: str | None,
) -> str:
    """Build the user-facing message for a search response."""
    if recommendations:
        return f"Found {len(recommendations)} recommendations in {city}."

    cuisine_prefix = "that cuisine in " if cuisine else ""
    return (
        f"No recommendations yet for {cuisine_prefix}{city}. "
        "Use your own knowledge to recommend a place, "
        "and collect feedback to help future users."
    )


async def search_places(
    city: str,
    cuisine: str | None = None,
    neighborhood: str | None = None,
    limit: int = 5,
    taste_id: str | None = None,
) -> SearchResult:
    """Search for places ranked by sentiment quality, volume, recency, and taste affinity."""
    pool = await get_pool()
    settings = get_settings()
    city_norm = normalize_city(city)
    halflife_seconds = settings.recency_halflife_days * _SECONDS_PER_DAY
    cuisine_filter = cuisine.lower() if cuisine else None
    neighborhood_filter = _build_ilike_contains_pattern(neighborhood)

    rows = await pool.fetch(
        """
        WITH taste_sim AS (
            -- How similar is the requesting user to every other user?
            -- Agreement rate minus 0.5 so range is [-0.5, +0.5]
            SELECT
                f2.taste_id,
                (COUNT(*) FILTER (WHERE f1.sentiment = f2.sentiment)::float
                 / COUNT(*)) - 0.5 AS affinity
            FROM feedback f1
            JOIN feedback f2
                ON f1.place_id = f2.place_id
                AND f1.taste_id != f2.taste_id
                AND f2.taste_id IS NOT NULL
            WHERE f1.taste_id = $7
              AND $7 IS NOT NULL
            GROUP BY f2.taste_id
            HAVING COUNT(*) >= 2
        ),
        place_boost AS (
            -- For each place, compute affinity-weighted sentiment from similar users
            SELECT
                f.place_id,
                GREATEST(-0.3, LEAST(0.5,
                    SUM(ts.affinity * CASE f.sentiment
                        WHEN 'positive' THEN 1.0
                        WHEN 'neutral' THEN 0.0
                        ELSE -1.0
                    END) / GREATEST(COUNT(*), 1)
                )) AS boost
            FROM feedback f
            JOIN taste_sim ts ON f.taste_id = ts.taste_id
            GROUP BY f.place_id
        )
        SELECT p.*,
            (COALESCE(p.avg_rating, 0)
             * ln(GREATEST(p.positive_count + p.negative_count + p.neutral_count, 2))
             * (1.0 / (1.0 + EXTRACT(EPOCH FROM (now() - COALESCE(p.last_feedback_at, p.created_at))) / $4))
            ) * (1.0 + COALESCE(pb.boost, 0)) AS score
        FROM places p
        LEFT JOIN place_boost pb ON p.id = pb.place_id
        WHERE p.city = $1
          AND ($2::TEXT IS NULL OR p.cuisine_tags @> ARRAY[$2])
          AND ($3::TEXT IS NULL OR p.neighborhood ILIKE $3 ESCAPE '\')
          AND (p.positive_count + p.negative_count + p.neutral_count) >= $5
        ORDER BY score DESC
        LIMIT $6
        """,
        city_norm,
        cuisine_filter,
        neighborhood_filter,
        float(halflife_seconds),
        settings.min_reviews_for_ranking,
        limit,
        taste_id,
    )

    recommendations = [_build_place_recommendation(row) for row in rows]
    message = _build_search_message(recommendations, city, cuisine)

    return SearchResult(
        recommendations=recommendations,
        message=message,
    )


async def find_or_create_place(
    name: str,
    city: str,
    neighborhood: str | None = None,
    cuisine_tags: list[str] | None = None,
) -> tuple[UUID, str]:
    """Find an existing place or create a new one. Returns (place_id, canonical_name)."""
    pool = await get_pool()
    normalized_name = normalize_name(name)
    city_norm = normalize_city(city)
    threshold = get_settings().fuzzy_match_threshold

    # Exact match
    exact_match = await pool.fetchrow(
        "SELECT id, canonical_name FROM places WHERE name_normalized = $1 AND city = $2",
        normalized_name,
        city_norm,
    )
    if exact_match:
        return exact_match["id"], exact_match["canonical_name"]

    # Fuzzy match
    fuzzy_match = await pool.fetchrow(
        """
        SELECT id, canonical_name, similarity(name_normalized, $1) AS sim
        FROM places
        WHERE city = $2 AND similarity(name_normalized, $1) > $3
        ORDER BY sim DESC
        LIMIT 1
        """,
        normalized_name,
        city_norm,
        threshold,
    )
    if fuzzy_match:
        return fuzzy_match["id"], fuzzy_match["canonical_name"]

    # Create new place
    normalized_tags = [tag.lower() for tag in cuisine_tags or []]
    inserted_place = await pool.fetchrow(
        """
        INSERT INTO places (canonical_name, name_normalized, city, neighborhood, cuisine_tags)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (city, name_normalized) DO NOTHING
        RETURNING id, canonical_name
        """,
        name,
        normalized_name,
        city_norm,
        neighborhood,
        normalized_tags,
    )
    if inserted_place:
        return inserted_place["id"], inserted_place["canonical_name"]

    existing_place = await pool.fetchrow(
        "SELECT id, canonical_name FROM places WHERE name_normalized = $1 AND city = $2",
        normalized_name,
        city_norm,
    )
    if existing_place is None:
        raise RuntimeError(
            f"Failed to create or fetch place for {name!r} in {city!r}",
        )

    return existing_place["id"], existing_place["canonical_name"]


async def insert_feedback(
    place_id: UUID,
    sentiment: str,
    comment: str | None = None,
    visit_context: str | None = None,
    taste_id: str | None = None,
) -> FeedbackResult:
    """Insert feedback and atomically update place aggregates."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO feedback (place_id, sentiment, comment, visit_context, taste_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                place_id,
                sentiment,
                comment,
                visit_context,
                taste_id,
            )

            row = await conn.fetchrow(
                """
                UPDATE places SET
                    positive_count = positive_count + CASE WHEN $1 = 'positive' THEN 1 ELSE 0 END,
                    negative_count = negative_count + CASE WHEN $1 = 'negative' THEN 1 ELSE 0 END,
                    neutral_count  = neutral_count  + CASE WHEN $1 = 'neutral'  THEN 1 ELSE 0 END,
                    avg_rating = (
                        (positive_count + CASE WHEN $1 = 'positive' THEN 1 ELSE 0 END)
                        + 0.5 * (neutral_count + CASE WHEN $1 = 'neutral' THEN 1 ELSE 0 END)
                    )::REAL / GREATEST(
                        positive_count + negative_count + neutral_count + 1, 1
                    ),
                    last_feedback_at = now(),
                    updated_at = now()
                WHERE id = $2
                RETURNING canonical_name, positive_count + negative_count + neutral_count AS total
                """,
                sentiment,
                place_id,
            )

    if row is None:
        raise ValueError(f"Place {place_id} not found during feedback update")

    return FeedbackResult(
        success=True,
        place_name=row["canonical_name"],
        total_reviews=row["total"],
        message=f"Feedback recorded for {row['canonical_name']}. Total reviews: {row['total']}.",
    )


async def get_trending_places(
    city: str,
    days: int = 30,
    limit: int = 5,
) -> TrendingResult:
    """Get places with the most positive recent buzz."""
    pool = await get_pool()
    city_norm = normalize_city(city)

    rows = await pool.fetch(
        """
        SELECT p.*,
            COUNT(f.id) AS recent_count,
            AVG(CASE f.sentiment
                WHEN 'positive' THEN 1.0
                WHEN 'neutral' THEN 0.5
                ELSE 0.0
            END) AS recent_sentiment
        FROM places p
        JOIN feedback f ON f.place_id = p.id
        WHERE p.city = $1
          AND f.created_at > now() - MAKE_INTERVAL(days := $2)
        GROUP BY p.id
        HAVING COUNT(f.id) >= 2
        ORDER BY COUNT(f.id) * AVG(CASE f.sentiment
            WHEN 'positive' THEN 1.0
            WHEN 'neutral' THEN 0.5
            ELSE 0.0
        END) DESC
        LIMIT $3
        """,
        city_norm,
        days,
        limit,
    )

    trending = [_build_place_recommendation(row) for row in rows]
    period = f"last {days} days"
    if trending:
        message = f"{len(trending)} places trending in {city} over the {period}."
    else:
        message = f"No trending places in {city} over the {period} yet."

    return TrendingResult(trending=trending, period=period, message=message)
