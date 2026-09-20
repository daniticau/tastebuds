"""Ranking: pure functions, no database.

SQL gathers the signals for each candidate place. This module turns the signals
into one score and a list of reasons. Pure code keeps the ranking easy to test.

score = quality * confidence * freshness * (1 + personal_fit)

- quality: share of good opinions, pulled toward a prior when opinions are few.
  One rave does not beat nine raves and one complaint.
- confidence: a small bonus for volume.
- freshness: old praise counts less, but never less than 70%.
- personal_fit: friends, taste neighbors, circle, profile, occasion, price, and distance.
  Friends count most: a person trusts the people they talk to every day.
"""

import math
from dataclasses import dataclass, field

_FRESHNESS_FLOOR = 0.7
_CONFIDENCE_WEIGHT = 0.12

_NEIGHBOR_BOOST_RANGE = (-0.3, 0.5)
_PERSONAL_FIT_RANGE = (-0.6, 1.0)

_FRIEND_WEIGHT = 0.6
_CIRCLE_WEIGHT = 0.3
_LIKED_CUISINE_BOOST = 0.15
_DISLIKED_CUISINE_PENALTY = -0.5
_LEARNED_CUISINE_WEIGHT = 0.15
_DIETARY_MATCH_BOOST = 0.2
_OCCASION_WEIGHT = 0.25
_VIBE_WEIGHT = 0.15
_NEIGHBORHOOD_BOOST = 0.4
_SIMILAR_PLACE_WEIGHT = 0.35
_PRICE_MATCH_BOOST = 0.08
_PRICE_MISMATCH_PENALTY = -0.15
_NEAR_BOOST = 0.2
_NEAR_KM = 2.0
_FAR_KM = 15.0
_TOO_FAR_KM = 30.0
_TOO_FAR_PENALTY = -0.2

_EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class RankingConfig:
    prior_mean: float = 0.6
    prior_weight: float = 3.0
    halflife_days: float = 120.0


@dataclass
class TasteContext:
    """What the engine knows about the person who asks."""

    dietary: list[str] = field(default_factory=list)
    liked_cuisines: list[str] = field(default_factory=list)
    disliked_cuisines: list[str] = field(default_factory=list)
    vibes: list[str] = field(default_factory=list)
    budget: int | None = None
    # Cuisine tag -> affinity in [-1, 1], learned from the person's own opinions.
    learned_cuisines: dict[str, float] = field(default_factory=dict)


@dataclass
class QueryContext:
    """What the person asks for right now."""

    cuisine_terms: list[str] = field(default_factory=list)
    neighborhood: str | None = None
    occasion: str | None = None
    vibes: list[str] = field(default_factory=list)
    max_price: int | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Candidate:
    """One place plus every signal the ranking reads."""

    positive: int = 0
    neutral: int = 0
    negative: int = 0
    days_since_feedback: float = 0.0
    cuisine_tags: list[str] = field(default_factory=list)
    neighborhood: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price_level: float | None = None
    # kind -> tag -> mention count, for kinds 'occasion', 'vibe', 'dietary'
    tags: dict[str, dict[str, int]] = field(default_factory=dict)
    neighbor_boost: float = 0.0
    neighbor_count: int = 0
    circle_likes: int = 0
    circle_dislikes: int = 0
    # Friend opinions, weighted by closeness: 0.5, 1.0, or 2.0 per friend.
    friend_like_weight: float = 0.0
    friend_dislike_weight: float = 0.0
    friend_likes: int = 0
    similar_likes: int = 0


@dataclass
class Score:
    value: float
    reasons: list[str]
    distance_km: float | None = None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def bayesian_quality(positive: int, neutral: int, negative: int, config: RankingConfig) -> float:
    """Share of good opinions, shrunk toward the prior when the sample is small."""
    total = positive + neutral + negative
    weighted = positive + 0.5 * neutral + config.prior_mean * config.prior_weight
    return weighted / (total + config.prior_weight)


def confidence_bonus(total: int) -> float:
    return 1.0 + _CONFIDENCE_WEIGHT * math.log1p(total)


def freshness(days_since_feedback: float, config: RankingConfig) -> float:
    decay = 0.5 ** (max(days_since_feedback, 0.0) / config.halflife_days)
    return _FRESHNESS_FLOOR + (1.0 - _FRESHNESS_FLOOR) * decay


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def confidence_label(total: int) -> str:
    """How much the agent may lean on this place: 'low', 'medium', or 'high'."""
    if total >= 8:
        return "high"
    if total >= 3:
        return "medium"
    return "low"


def _tag_share(tags: dict[str, int], wanted: str, total_opinions: int) -> float:
    """How strongly people attach a tag to a place, in [0, 1]."""
    mentions = tags.get(wanted, 0)
    if mentions <= 0:
        return 0.0
    return min(1.0, mentions / max(total_opinions, 1) + 0.25)


def _distance_fit(distance_km: float) -> float:
    if distance_km <= _NEAR_KM:
        return _NEAR_BOOST
    if distance_km >= _TOO_FAR_KM:
        return _TOO_FAR_PENALTY
    if distance_km >= _FAR_KM:
        return 0.0
    return _NEAR_BOOST * (_FAR_KM - distance_km) / (_FAR_KM - _NEAR_KM)


def _cuisine_fit(candidate: Candidate, taste: TasteContext, query: QueryContext) -> tuple[float, str | None]:
    tags = set(candidate.cuisine_tags)
    asked_for = set(query.cuisine_terms)

    # A disliked cuisine sinks a place, unless the person asks for that cuisine today.
    if tags & set(taste.disliked_cuisines) and not tags & asked_for:
        return _DISLIKED_CUISINE_PENALTY, None

    fit = 0.0
    reason = None
    if tags & set(taste.liked_cuisines):
        fit += _LIKED_CUISINE_BOOST
        reason = "matches cuisines they like"

    learned = [taste.learned_cuisines[tag] for tag in tags if tag in taste.learned_cuisines]
    if learned:
        learned_fit = _LEARNED_CUISINE_WEIGHT * (sum(learned) / len(learned))
        fit += learned_fit
        if learned_fit > 0.03 and reason is None:
            reason = "similar to places they enjoyed before"
    return fit, reason


def score_candidate(
    candidate: Candidate,
    taste: TasteContext,
    query: QueryContext,
    config: RankingConfig,
) -> Score:
    """Score one place for one person and one request."""
    total = candidate.positive + candidate.neutral + candidate.negative
    base = (
        bayesian_quality(candidate.positive, candidate.neutral, candidate.negative, config)
        * confidence_bonus(total)
        * freshness(candidate.days_since_feedback, config)
    )

    fit = 0.0
    reasons: list[str] = []

    neighbor = clamp(candidate.neighbor_boost, *_NEIGHBOR_BOOST_RANGE)
    fit += neighbor
    if neighbor > 0.05:
        reasons.append("people with similar taste liked it")
    elif neighbor < -0.05:
        reasons.append("people with similar taste were not impressed")

    friend_weight = candidate.friend_like_weight + candidate.friend_dislike_weight
    if friend_weight:
        net = candidate.friend_like_weight - candidate.friend_dislike_weight
        fit += _FRIEND_WEIGHT * net / (friend_weight + 1)
        if candidate.friend_likes == 1:
            reasons.append("someone close to them liked it")
        elif candidate.friend_likes > 1:
            reasons.append(f"{candidate.friend_likes} people close to them liked it")

    circle_votes = candidate.circle_likes + candidate.circle_dislikes
    if circle_votes:
        net = candidate.circle_likes - candidate.circle_dislikes
        fit += _CIRCLE_WEIGHT * net / (circle_votes + 1)
        if candidate.circle_likes:
            reasons.append(f"{candidate.circle_likes} in their circle liked it")

    if candidate.similar_likes:
        fit += _SIMILAR_PLACE_WEIGHT * candidate.similar_likes / (candidate.similar_likes + 1)
        reasons.append("fans of the place they named also like this one")

    cuisine_fit, cuisine_reason = _cuisine_fit(candidate, taste, query)
    fit += cuisine_fit
    if cuisine_reason:
        reasons.append(cuisine_reason)

    dietary_tags = candidate.tags.get("dietary", {})
    matched_diets = [diet for diet in taste.dietary if dietary_tags.get(diet, 0) > 0]
    if matched_diets:
        fit += _DIETARY_MATCH_BOOST
        reasons.append(f"known to work for {', '.join(matched_diets)}")

    if query.occasion:
        share = _tag_share(candidate.tags.get("occasion", {}), query.occasion, total)
        if share:
            fit += _OCCASION_WEIGHT * share
            reasons.append(f"people go there for {query.occasion}")

    wanted_vibes = query.vibes or taste.vibes
    vibe_tags = candidate.tags.get("vibe", {})
    matched_vibes = [vibe for vibe in wanted_vibes if vibe_tags.get(vibe, 0) > 0]
    if matched_vibes:
        best = max(_tag_share(vibe_tags, vibe, total) for vibe in matched_vibes)
        fit += _VIBE_WEIGHT * best
        reasons.append(f"vibe: {', '.join(matched_vibes)}")

    if query.neighborhood and candidate.neighborhood:
        if query.neighborhood.lower() in candidate.neighborhood.lower():
            fit += _NEIGHBORHOOD_BOOST
            reasons.append(f"in {candidate.neighborhood}")

    budget = query.max_price or taste.budget
    if budget and candidate.price_level:
        gap = candidate.price_level - budget
        if abs(gap) < 0.75:
            fit += _PRICE_MATCH_BOOST
        elif gap >= 1.5:
            fit += _PRICE_MISMATCH_PENALTY

    distance_km = None
    if None not in (query.latitude, query.longitude, candidate.latitude, candidate.longitude):
        distance_km = haversine_km(
            query.latitude, query.longitude, candidate.latitude, candidate.longitude
        )
        distance_fit = _distance_fit(distance_km)
        fit += distance_fit
        if distance_fit >= _NEAR_BOOST:
            reasons.append("close by")

    fit = clamp(fit, *_PERSONAL_FIT_RANGE)
    return Score(value=base * (1.0 + fit), reasons=reasons, distance_km=distance_km)


def learned_cuisine_affinity(history: list[tuple[list[str], str]]) -> dict[str, float]:
    """Learn cuisine affinity from a person's own opinions.

    history holds (cuisine_tags, sentiment) pairs. The +2 in the divisor keeps
    one good ramen night from turning into a strong ramen preference.
    """
    net: dict[str, float] = {}
    counts: dict[str, int] = {}
    values = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

    for cuisine_tags, sentiment in history:
        for tag in cuisine_tags:
            net[tag] = net.get(tag, 0.0) + values.get(sentiment, 0.0)
            counts[tag] = counts.get(tag, 0) + 1

    return {tag: net[tag] / (counts[tag] + 2) for tag in net}
