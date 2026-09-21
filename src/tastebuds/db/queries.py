import json
from dataclasses import dataclass, field
from uuid import UUID

import asyncpg

from tastebuds import decisions
from tastebuds.config import get_settings
from tastebuds.db.client import get_pool
from tastebuds.db.models import (
    FeedbackResult,
    PlaceRecommendation,
    SearchResult,
    TrendingResult,
)
from tastebuds.normalizer import (
    is_generic_name,
    is_short_form,
    normalize_city,
    normalize_dish,
    normalize_name,
)
from tastebuds.ranking import (
    Candidate,
    QueryContext,
    RankingConfig,
    Score,
    TasteContext,
    confidence_label,
    score_candidate,
)
from tastebuds.taxonomy import (
    cuisine_search_terms,
    cuisine_tags_for_place,
    infer_cuisines_from_name,
)

_MAX_CUISINE_TAGS_PER_PLACE = 12
_MAX_DISHES_PER_FEEDBACK = 6
_NAME_LOOKUP_SIMILARITY = 0.35
_TRACKED_RECOMMENDATIONS = 3
_SENTIMENT_COLUMNS = {
    "positive": "positive_count",
    "negative": "negative_count",
    "neutral": "neutral_count",
}


class FeedbackLimitError(ValueError):
    """One token sent more opinions in a day than a person plausibly has."""


@dataclass
class DishOpinion:
    name: str
    sentiment: str = "positive"


@dataclass
class FeedbackDetails:
    """Optional signals that ride along with one opinion."""

    comment: str | None = None
    visit_context: str | None = None
    occasion: str | None = None
    price_level: int | None = None
    dishes: list[DishOpinion] = field(default_factory=list)
    vibe_tags: list[str] = field(default_factory=list)
    dietary_tags: list[str] = field(default_factory=list)
    source: str = "conversation"
    platform: str | None = None


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


def _price_level(row: dict) -> float | None:
    if not row["price_count"]:
        return None
    return row["price_sum"] / row["price_count"]


def _split_tags(raw: str | dict | None) -> dict[str, dict[str, int]]:
    """Turn {'occasion:date night': 3} into {'occasion': {'date night': 3}}."""
    if not raw:
        return {}

    flat = json.loads(raw) if isinstance(raw, str) else raw
    tags: dict[str, dict[str, int]] = {}
    for key, count in flat.items():
        kind, _, tag = key.partition(":")
        tags.setdefault(kind, {})[tag] = count
    return tags


def _top_tags(tags: dict[str, int], limit: int = 3) -> list[str]:
    ranked = sorted(tags.items(), key=lambda item: item[1], reverse=True)
    return [tag for tag, _count in ranked[:limit]]


_OWN_HISTORY_LABELS = {
    "positive": "they loved it before",
    "neutral": "they found it just okay before",
    "negative": "they did not like it before",
}


def _build_place_recommendation(
    row: dict,
    score: Score | None = None,
    dishes: list[dict] | None = None,
    notes: list[str] | None = None,
) -> PlaceRecommendation:
    """Convert a database row into the public recommendation shape."""
    total_reviews = _count_reviews(row)
    positive_pct = row["positive_count"] / max(total_reviews, 1)
    tags = _split_tags(row.get("tags"))
    price = _price_level(row)

    order_this = []
    skip_this = []
    for dish in dishes or []:
        if dish["positive_count"] > dish["negative_count"]:
            order_this.append(dish["display_name"])
        elif dish["negative_count"] > dish["positive_count"]:
            skip_this.append(dish["display_name"])

    return PlaceRecommendation(
        name=row["canonical_name"],
        city=row["city"],
        neighborhood=row["neighborhood"],
        address=row["address"],
        cuisine_tags=row["cuisine_tags"],
        sentiment_summary=compute_sentiment_summary(positive_pct, total_reviews),
        positive_pct=round(positive_pct, 2),
        total_reviews=total_reviews,
        confidence=confidence_label(total_reviews),
        order_this=order_this[:3],
        skip_this=skip_this[:2],
        price_level=round(price) if price else None,
        good_for=_top_tags(tags.get("occasion", {})),
        vibes=_top_tags(tags.get("vibe", {})),
        dietary_fit=_top_tags(tags.get("dietary", {}), limit=5),
        distance_km=round(score.distance_km, 1) if score and score.distance_km is not None else None,
        your_history=_OWN_HISTORY_LABELS.get(row.get("own_sentiment")),
        why=score.reasons if score else [],
        notes=notes or [],
        last_reviewed=(
            row["last_feedback_at"].isoformat()
            if row["last_feedback_at"]
            else None
        ),
    )


def _build_search_message(
    recommendations: list[PlaceRecommendation],
    city: str,
    cuisine: str | None,
) -> str:
    """Build the agent-facing message for a search response."""
    if recommendations:
        return f"Found {len(recommendations)} recommendations in {city}."

    cuisine_prefix = "that cuisine in " if cuisine else ""
    return (
        f"No recommendations yet for {cuisine_prefix}{city}. "
        "Use your own knowledge to recommend a place, "
        "and log how it went so the next person gets a better answer."
    )


def _candidate_from_row(row: dict) -> Candidate:
    return Candidate(
        positive=row["positive_count"],
        neutral=row["neutral_count"],
        negative=row["negative_count"],
        days_since_feedback=float(row["days_since_feedback"]),
        cuisine_tags=row["cuisine_tags"] or [],
        neighborhood=row["neighborhood"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        price_level=_price_level(row),
        tags=_split_tags(row["tags"]),
        neighbor_boost=float(row["neighbor_boost"] or 0.0),
        neighbor_count=row["neighbor_count"] or 0,
        circle_likes=row["circle_likes"] or 0,
        circle_dislikes=row["circle_dislikes"] or 0,
        friend_like_weight=float(row["friend_like_weight"] or 0.0),
        friend_dislike_weight=float(row["friend_dislike_weight"] or 0.0),
        friend_likes=row["friend_likes"] or 0,
        similar_likes=row["similar_likes"] or 0,
    )


_CANDIDATES_SQL = """
WITH mine AS (
    -- The asker's own active opinions, one per place.
    SELECT DISTINCT ON (place_id) place_id, sentiment
    FROM feedback
    WHERE taste_id = $1::TEXT AND superseded_at IS NULL
    ORDER BY place_id, created_at DESC
),
taste_sim AS (
    -- How much does each other person agree with the asker?
    -- The +2 shrinks the score when the overlap is small.
    SELECT
        f.taste_id,
        SUM(CASE
            WHEN f.sentiment = m.sentiment AND f.sentiment <> 'neutral' THEN 1.0
            WHEN f.sentiment = m.sentiment THEN 0.5
            WHEN f.sentiment = 'neutral' OR m.sentiment = 'neutral' THEN 0.0
            ELSE -1.0
        END) / (COUNT(*) + 2) AS affinity
    FROM mine m
    JOIN feedback f
        ON f.place_id = m.place_id
        AND f.taste_id IS NOT NULL
        AND f.taste_id <> $1::TEXT
        AND f.superseded_at IS NULL
    GROUP BY f.taste_id
),
neighbor_boost AS (
    -- For each place: what do the asker's taste neighbors think of it?
    SELECT
        f.place_id,
        SUM(ts.affinity * CASE f.sentiment
            WHEN 'positive' THEN 1.0
            WHEN 'neutral' THEN 0.0
            ELSE -1.0
        END) / (COUNT(*) + 1) AS boost,
        COUNT(*) AS neighbors
    FROM feedback f
    JOIN taste_sim ts ON ts.taste_id = f.taste_id
    WHERE f.superseded_at IS NULL
    GROUP BY f.place_id
),
my_circles AS (
    -- Small circles stay silent, or "one person liked it" would name the person.
    SELECT cm.circle_id
    FROM circle_members cm
    WHERE cm.taste_id = $1::TEXT
      AND (SELECT COUNT(*) FROM circle_members x WHERE x.circle_id = cm.circle_id) >= $2
),
circle_votes AS (
    SELECT
        f.place_id,
        COUNT(DISTINCT f.taste_id) FILTER (WHERE f.sentiment = 'positive') AS likes,
        COUNT(DISTINCT f.taste_id) FILTER (WHERE f.sentiment = 'negative') AS dislikes
    FROM feedback f
    JOIN circle_members cm ON cm.taste_id = f.taste_id
    WHERE cm.circle_id IN (SELECT circle_id FROM my_circles)
      AND f.taste_id <> $1::TEXT
      AND f.superseded_at IS NULL
    GROUP BY f.place_id
),
friend_votes AS (
    -- What do the asker's linked friends think? Closer friends weigh more.
    -- With fewer than $10 friends the signal stays off, or it would name the friend.
    SELECT
        f.place_id,
        COALESCE(SUM(w.weight) FILTER (WHERE f.sentiment = 'positive'), 0) AS like_weight,
        COALESCE(SUM(w.weight) FILTER (WHERE f.sentiment = 'negative'), 0) AS dislike_weight,
        COUNT(*) FILTER (WHERE f.sentiment = 'positive') AS likes
    FROM friend_ties ft
    JOIN feedback f ON f.taste_id = ft.friend_taste_id AND f.superseded_at IS NULL
    CROSS JOIN LATERAL (
        SELECT CASE ft.closeness WHEN 3 THEN 2.0 WHEN 2 THEN 1.0 ELSE 0.5 END AS weight
    ) w
    WHERE ft.taste_id = $1::TEXT
      AND (SELECT COUNT(*) FROM friend_ties x WHERE x.taste_id = $1::TEXT) >= $10
    GROUP BY f.place_id
),
similar_places AS (
    -- "Somewhere like X": places that fans of X also like.
    SELECT f2.place_id, COUNT(DISTINCT f2.taste_id) AS likes
    FROM feedback f1
    JOIN feedback f2
        ON f2.taste_id = f1.taste_id
        AND f2.place_id <> f1.place_id
    WHERE f1.place_id = $3::UUID
      AND f1.taste_id IS NOT NULL
      AND f1.sentiment = 'positive' AND f2.sentiment = 'positive'
      AND f1.superseded_at IS NULL AND f2.superseded_at IS NULL
    GROUP BY f2.place_id
)
SELECT
    p.*,
    nb.boost AS neighbor_boost,
    nb.neighbors AS neighbor_count,
    cv.likes AS circle_likes,
    cv.dislikes AS circle_dislikes,
    sp.likes AS similar_likes,
    fv.like_weight AS friend_like_weight,
    fv.dislike_weight AS friend_dislike_weight,
    fv.likes AS friend_likes,
    m.sentiment AS own_sentiment,
    EXTRACT(EPOCH FROM (now() - COALESCE(p.last_feedback_at, p.created_at))) / 86400.0
        AS days_since_feedback,
    (
        SELECT jsonb_object_agg(pt.kind || ':' || pt.tag, pt.mention_count)
        FROM place_tags pt
        WHERE pt.place_id = p.id
    ) AS tags
FROM places p
LEFT JOIN neighbor_boost nb ON nb.place_id = p.id
LEFT JOIN circle_votes cv ON cv.place_id = p.id
LEFT JOIN similar_places sp ON sp.place_id = p.id
LEFT JOIN friend_votes fv ON fv.place_id = p.id
LEFT JOIN mine m ON m.place_id = p.id
WHERE p.city = $4
  AND ($5::TEXT[] IS NULL OR p.cuisine_tags && $5::TEXT[])
  AND (p.positive_count + p.negative_count + p.neutral_count) >= $6
  AND ($3::UUID IS NULL OR p.id <> $3::UUID)
  AND ($7::TEXT IS NULL OR similarity(p.name_normalized, $7::TEXT) > $8)
  AND (NOT $11::BOOLEAN OR COALESCE(fv.likes, 0) + COALESCE(cv.likes, 0) > 0)
ORDER BY
    (p.positive_count + 0.5 * p.neutral_count + 1.8)
    / (p.positive_count + p.negative_count + p.neutral_count + 3.0) DESC
LIMIT $9
"""


async def _fetch_place_details(
    pool: asyncpg.Pool,
    place_ids: list[UUID],
    taste_id: str | None,
) -> tuple[dict[UUID, list[dict]], dict[UUID, list[str]]]:
    """Fetch dishes and recent notes for the places that made the final list."""
    if not place_ids:
        return {}, {}

    dish_rows = await pool.fetch(
        """
        SELECT place_id, display_name, positive_count, negative_count, neutral_count
        FROM place_dishes
        WHERE place_id = ANY($1::UUID[])
        ORDER BY (positive_count + negative_count + neutral_count) DESC, last_mentioned_at DESC
        """,
        place_ids,
    )
    note_rows = await pool.fetch(
        """
        SELECT place_id, comment
        FROM (
            SELECT place_id, comment,
                ROW_NUMBER() OVER (PARTITION BY place_id ORDER BY created_at DESC) AS row_num
            FROM feedback
            WHERE place_id = ANY($1::UUID[])
              AND comment IS NOT NULL
              AND superseded_at IS NULL
              AND taste_id IS DISTINCT FROM $2::TEXT
        ) recent
        WHERE row_num <= 2
        """,
        place_ids,
        taste_id,
    )

    dishes: dict[UUID, list[dict]] = {}
    for row in dish_rows:
        dishes.setdefault(row["place_id"], []).append(dict(row))

    notes: dict[UUID, list[str]] = {}
    for row in note_rows:
        notes.setdefault(row["place_id"], []).append(row["comment"])

    return dishes, notes


async def _record_recommendations(
    pool: asyncpg.Pool,
    taste_id: str,
    place_ids: list[UUID],
) -> None:
    """Remember what the engine recommended, so the agent can ask about it later."""
    tracked = place_ids[:_TRACKED_RECOMMENDATIONS]
    if not tracked:
        return

    await pool.execute(
        """
        INSERT INTO recommendation_events (taste_id, place_id, rank)
        SELECT $1, shown.place_id, shown.rank
        FROM unnest($2::UUID[], $3::SMALLINT[]) AS shown(place_id, rank)
        WHERE NOT EXISTS (
            SELECT 1 FROM recommendation_events e
            WHERE e.taste_id = $1
              AND e.place_id = shown.place_id
              AND e.resolved_at IS NULL
              AND e.created_at > now() - INTERVAL '7 days'
        )
        """,
        taste_id,
        tracked,
        list(range(1, len(tracked) + 1)),
    )


async def _find_place_id(pool: asyncpg.Pool, name: str, city_norm: str) -> UUID | None:
    """Find an existing place by name, without creating one."""
    normalized_name = normalize_name(name)
    if not normalized_name:
        return None

    return await pool.fetchval(
        """
        SELECT id FROM places
        WHERE city = $2 AND similarity(name_normalized, $1) > $3
        ORDER BY similarity(name_normalized, $1) DESC
        LIMIT 1
        """,
        normalized_name,
        city_norm,
        get_settings().fuzzy_match_threshold,
    )


async def search_places(
    city: str,
    cuisine: str | None = None,
    neighborhood: str | None = None,
    limit: int = 5,
    taste_id: str | None = None,
    *,
    taste: TasteContext | None = None,
    occasion: str | None = None,
    vibes: list[str] | None = None,
    max_price: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    similar_to: str | None = None,
    place_name: str | None = None,
    new_places_only: bool = False,
    friends_only: bool = False,
) -> SearchResult:
    """Search for places, ranked for the person who asks."""
    pool = await get_pool()
    settings = get_settings()
    city_norm = normalize_city(city)
    taste = taste or TasteContext()

    cuisine_terms = cuisine_search_terms(cuisine) if cuisine else []
    similar_place_id = await _find_place_id(pool, similar_to, city_norm) if similar_to else None
    place_name_norm = normalize_name(place_name) if place_name else None

    rows = await pool.fetch(
        _CANDIDATES_SQL,
        taste_id,
        settings.circle_min_members,
        similar_place_id,
        city_norm,
        cuisine_terms or None,
        # A direct question about one place deserves an answer even when data is thin.
        0 if place_name_norm else settings.min_reviews_for_ranking,
        place_name_norm,
        _NAME_LOOKUP_SIMILARITY,
        settings.candidate_pool_size,
        settings.friend_min_ties,
        friends_only,
    )

    config = RankingConfig(
        prior_mean=settings.quality_prior_mean,
        prior_weight=settings.quality_prior_weight,
        halflife_days=float(settings.recency_halflife_days),
    )
    query = QueryContext(
        cuisine_terms=cuisine_terms,
        neighborhood=neighborhood,
        occasion=occasion,
        vibes=vibes or [],
        max_price=max_price,
        latitude=latitude,
        longitude=longitude,
    )

    scored: list[tuple[Score, dict]] = []
    for row in rows:
        own_sentiment = row["own_sentiment"]
        if not place_name_norm:
            # Never send a person back to a place they disliked.
            if own_sentiment == "negative":
                continue
            if new_places_only and own_sentiment is not None:
                continue
        scored.append((score_candidate(_candidate_from_row(row), taste, query, config), dict(row)))

    scored.sort(key=lambda pair: pair[0].value, reverse=True)
    top = scored[:limit]
    top_ids = [row["id"] for _score, row in top]

    dishes, notes = await _fetch_place_details(pool, top_ids, taste_id)
    recommendations = [
        _build_place_recommendation(row, score, dishes.get(row["id"]), notes.get(row["id"]))
        for score, row in top
    ]

    if taste_id and not place_name_norm:
        await _record_recommendations(pool, taste_id, top_ids)

    return SearchResult(
        recommendations=recommendations,
        message=_build_search_message(recommendations, city, cuisine),
    )


async def _match_similar_place(
    pool: asyncpg.Pool,
    *,
    name: str,
    normalized_name: str,
    city: str,
    city_norm: str,
    neighborhood: str | None,
    hints: list[str],
    need_cuisine: bool,
) -> tuple[asyncpg.Record | None, str | None]:
    """Find a known place with a similar name. Returns (place, cuisine decided on the way).

    A strong name match decides alone. In the gray zone a name match cannot tell
    "Tajima" from "Tajima Ramen House" or "Pho Hoa" from "Pho Hoa Binh", so Jev decides.
    When Jev is off or gives no answer, two fixed rules decide: the similarity threshold,
    then the short-form rule.
    """
    settings = get_settings()
    similar = await pool.fetch(
        """
        SELECT id, canonical_name, name_normalized, neighborhood, cuisine_tags,
            similarity(name_normalized, $1) AS sim
        FROM places
        WHERE city = $2 AND similarity(name_normalized, $1) > $3
        ORDER BY sim DESC
        LIMIT 3
        """,
        normalized_name,
        city_norm,
        settings.dedup_review_floor,
    )
    best = similar[0] if similar else None
    if best and best["sim"] >= settings.dedup_auto_merge_similarity:
        return best, None

    decision = None
    if similar or need_cuisine:
        decision = await decisions.decide_place(
            name=name,
            city=city,
            neighborhood=neighborhood,
            hints=hints,
            candidates=[
                decisions.KnownPlace(row["canonical_name"], row["neighborhood"], row["cuisine_tags"])
                for row in similar
            ],
            need_cuisine=need_cuisine,
        )

    cuisine = decision.cuisine if decision else None
    if decision and decision.answered_sameness:
        return (similar[decision.same_as] if decision.same_as is not None else None), cuisine
    if best and best["sim"] > settings.fuzzy_match_threshold:
        return best, cuisine

    # A short form of exactly one known place: "Nonna Pia" for "Nonna Pia Trattoria".
    # Two matches would be a guess, so then the engine creates a new place instead.
    short_forms = [row for row in similar if is_short_form(normalized_name, row["name_normalized"])]
    if len(short_forms) == 1:
        return short_forms[0], cuisine
    return None, cuisine


async def find_or_create_place(
    name: str,
    city: str,
    neighborhood: str | None = None,
    cuisine_tags: list[str] | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    hints: list[str] | None = None,
) -> tuple[UUID, str]:
    """Find an existing place or create a new one. Returns (place_id, canonical_name).

    hints are dish names the person mentioned. They help decide the cuisine of a new place.
    """
    pool = await get_pool()
    normalized_name = normalize_name(name)
    if not normalized_name or is_generic_name(name):
        raise ValueError("Place name is too generic to identify a specific restaurant.")
    city_norm = normalize_city(city)
    if not city_norm:
        raise ValueError("A city is needed to identify the place.")
    tags = cuisine_tags_for_place(
        [*(cuisine_tags or []), *infer_cuisines_from_name(name)],
    )[:_MAX_CUISINE_TAGS_PER_PLACE]

    existing = await pool.fetchrow(
        "SELECT id, canonical_name FROM places WHERE name_normalized = $1 AND city = $2",
        normalized_name,
        city_norm,
    )
    if existing is None:
        existing, decided_cuisine = await _match_similar_place(
            pool,
            name=name,
            normalized_name=normalized_name,
            city=city,
            city_norm=city_norm,
            neighborhood=neighborhood,
            hints=hints or [],
            need_cuisine=not tags,
        )
        if decided_cuisine and not tags:
            tags = cuisine_tags_for_place([decided_cuisine])

    if existing is None:
        inserted = await pool.fetchrow(
            """
            INSERT INTO places (
                canonical_name, name_normalized, city, neighborhood, cuisine_tags,
                address, latitude, longitude
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (city, name_normalized) DO NOTHING
            RETURNING id, canonical_name
            """,
            name,
            normalized_name,
            city_norm,
            neighborhood,
            tags,
            address,
            latitude,
            longitude,
        )
        if inserted:
            return inserted["id"], inserted["canonical_name"]

        # Another request created the same place a moment ago.
        existing = await pool.fetchrow(
            "SELECT id, canonical_name FROM places WHERE name_normalized = $1 AND city = $2",
            normalized_name,
            city_norm,
        )
        if existing is None:
            raise RuntimeError(f"Failed to create or fetch place for {name!r} in {city!r}")

    # Each mention can teach the engine more about a known place.
    await pool.execute(
        """
        UPDATE places SET
            neighborhood = COALESCE(neighborhood, $2),
            address = COALESCE(address, $3),
            latitude = COALESCE(latitude, $4),
            longitude = COALESCE(longitude, $5),
            cuisine_tags = CASE
                WHEN cardinality(cuisine_tags) >= $7 THEN cuisine_tags
                ELSE ARRAY(SELECT DISTINCT tag FROM unnest(cuisine_tags || $6::TEXT[]) AS tag)
            END
        WHERE id = $1
        """,
        existing["id"],
        neighborhood,
        address,
        latitude,
        longitude,
        tags,
        _MAX_CUISINE_TAGS_PER_PLACE,
    )
    return existing["id"], existing["canonical_name"]


async def _supersede_previous_opinion(
    conn: asyncpg.Connection,
    place_id: UUID,
    taste_id: str,
) -> None:
    """One person, one active opinion per place: retire the older one."""
    previous = await conn.fetch(
        """
        UPDATE feedback SET superseded_at = now()
        WHERE taste_id = $1 AND place_id = $2 AND superseded_at IS NULL
        RETURNING sentiment, price_level
        """,
        taste_id,
        place_id,
    )
    for row in previous:
        column = _SENTIMENT_COLUMNS[row["sentiment"]]
        await conn.execute(
            f"""
            UPDATE places SET
                {column} = GREATEST({column} - 1, 0),
                price_sum = GREATEST(price_sum - $2, 0),
                price_count = GREATEST(price_count - $3, 0)
            WHERE id = $1
            """,
            place_id,
            row["price_level"] or 0,
            1 if row["price_level"] else 0,
        )


async def _record_tags_and_dishes(
    conn: asyncpg.Connection,
    place_id: UUID,
    details: FeedbackDetails,
) -> None:
    tagged = [("occasion", details.occasion)] if details.occasion else []
    tagged += [("vibe", tag) for tag in details.vibe_tags]
    tagged += [("dietary", tag) for tag in details.dietary_tags]

    if tagged:
        await conn.executemany(
            """
            INSERT INTO place_tags (place_id, kind, tag, mention_count)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (place_id, kind, tag)
            DO UPDATE SET mention_count = place_tags.mention_count + 1
            """,
            [(place_id, kind, tag) for kind, tag in tagged],
        )

    for dish in details.dishes[:_MAX_DISHES_PER_FEEDBACK]:
        dish_normalized = normalize_dish(dish.name)
        if not dish_normalized or dish.sentiment not in _SENTIMENT_COLUMNS:
            continue
        column = _SENTIMENT_COLUMNS[dish.sentiment]
        await conn.execute(
            f"""
            INSERT INTO place_dishes (place_id, dish_normalized, display_name, {column})
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (place_id, dish_normalized)
            DO UPDATE SET {column} = place_dishes.{column} + 1, last_mentioned_at = now()
            """,
            place_id,
            dish_normalized,
            dish.name.strip(),
        )


async def insert_feedback(
    place_id: UUID,
    sentiment: str,
    comment: str | None = None,
    visit_context: str | None = None,
    taste_id: str | None = None,
    details: FeedbackDetails | None = None,
) -> FeedbackResult:
    """Insert feedback and atomically update every aggregate that reads depend on."""
    if sentiment not in _SENTIMENT_COLUMNS:
        raise ValueError("Sentiment must be 'positive', 'negative', or 'neutral'.")

    pool = await get_pool()
    details = details or FeedbackDetails()
    details.comment = details.comment or comment
    details.visit_context = details.visit_context or visit_context
    sentiment_column = _SENTIMENT_COLUMNS[sentiment]

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock the place row so two opinions on one place cannot interleave.
            locked = await conn.fetchval("SELECT id FROM places WHERE id = $1 FOR UPDATE", place_id)
            if locked is None:
                raise ValueError(f"Place {place_id} not found during feedback update")

            if taste_id:
                sent_today = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM feedback
                    WHERE taste_id = $1 AND created_at > now() - INTERVAL '1 day'
                    """,
                    taste_id,
                )
                if sent_today >= get_settings().max_feedback_per_token_per_day:
                    raise FeedbackLimitError("Too much feedback from one source today.")
                await _supersede_previous_opinion(conn, place_id, taste_id)

            await conn.execute(
                """
                INSERT INTO feedback (
                    place_id, sentiment, comment, visit_context, taste_id,
                    dishes, occasion, price_level, vibe_tags, dietary_tags, source, platform
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6::JSONB, $7, $8, $9, $10, $11,
                    COALESCE($12, (SELECT platform FROM taste_profiles WHERE taste_id = $5))
                )
                """,
                place_id,
                sentiment,
                details.comment,
                details.visit_context,
                taste_id,
                json.dumps([{"name": d.name, "sentiment": d.sentiment} for d in details.dishes]),
                details.occasion,
                details.price_level,
                details.vibe_tags,
                details.dietary_tags,
                details.source,
                details.platform,
            )

            await conn.execute(
                f"""
                UPDATE places SET
                    {sentiment_column} = {sentiment_column} + 1,
                    price_sum = price_sum + $2,
                    price_count = price_count + $3,
                    last_feedback_at = now(),
                    updated_at = now()
                WHERE id = $1
                """,
                place_id,
                details.price_level or 0,
                1 if details.price_level else 0,
            )
            row = await conn.fetchrow(
                """
                UPDATE places SET
                    avg_rating = (positive_count + 0.5 * neutral_count)::REAL
                        / GREATEST(positive_count + negative_count + neutral_count, 1)
                WHERE id = $1
                RETURNING canonical_name, positive_count + negative_count + neutral_count AS total
                """,
                place_id,
            )

            await _record_tags_and_dishes(conn, place_id, details)

            if taste_id:
                await conn.execute(
                    """
                    UPDATE recommendation_events SET resolved_at = now()
                    WHERE taste_id = $1 AND place_id = $2 AND resolved_at IS NULL
                    """,
                    taste_id,
                    place_id,
                )
                await conn.execute(
                    "UPDATE taste_profiles SET last_seen_at = now() WHERE taste_id = $1",
                    taste_id,
                )

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
            (
                SELECT jsonb_object_agg(pt.kind || ':' || pt.tag, pt.mention_count)
                FROM place_tags pt
                WHERE pt.place_id = p.id
            ) AS tags
        FROM places p
        JOIN feedback f ON f.place_id = p.id
        WHERE p.city = $1
          AND f.created_at > now() - MAKE_INTERVAL(days := $2)
          AND f.superseded_at IS NULL
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

    dishes, notes = await _fetch_place_details(pool, [row["id"] for row in rows], None)
    trending = [
        _build_place_recommendation(
            dict(row), dishes=dishes.get(row["id"]), notes=notes.get(row["id"])
        )
        for row in rows
    ]
    period = f"last {days} days"
    if trending:
        message = (
            f"{len(trending)} places trending in {city} over the {period}. "
            'Credit the picks in a few words: "Tastebuds recommends <place>."'
        )
    else:
        message = f"No trending places in {city} over the {period} yet."

    return TrendingResult(trending=trending, period=period, message=message)
