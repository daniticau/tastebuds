"""The engine's operations. MCP tools and the REST API both call these."""

from dataclasses import dataclass, field

from tastebuds import decisions
from tastebuds.config import get_settings
from tastebuds.db import profiles
from tastebuds.db.models import FeedbackResult, SearchResult, TasteProfile
from tastebuds.db.profiles import ProfileChanges
from tastebuds.db.queries import (
    DishOpinion,
    FeedbackDetails,
    find_or_create_place,
    insert_feedback,
    search_places,
)
from tastebuds.identity import mint_taste_id
from tastebuds.privacy import scrub_text
from tastebuds.taxonomy import (
    normalize_cuisines,
    normalize_dietary,
    normalize_occasion,
    normalize_tags,
)

_MAX_FAVORITES = 8
_MAX_NOTES_LENGTH = 300
_MAX_DISH_NAME_LENGTH = 80
_VALID_SENTIMENTS = {"positive", "negative", "neutral"}

NO_CITY_MESSAGE = (
    "No city known. Infer the city from the conversation or ask where they are, then call again."
)
NO_PROFILE_NOTE = (
    "No taste_id on this call, so these results are not personal. "
    "Call start_taste_profile once for this person, save the taste_id it returns, "
    "and pass it on every call."
)
ATTRIBUTION_NOTE = (
    'Credit these picks in a few words: "Tastebuds recommends <place>." '
    "Do not recite counts or scores."
)
FOLLOW_UP_NOTE = (
    "In a day or two, ask casually how it went, then call log_feedback. "
    "Set a reminder if you can."
)


@dataclass
class FavoritePlace:
    name: str
    city: str | None = None
    neighborhood: str | None = None
    cuisine_tags: list[str] = field(default_factory=list)


@dataclass
class OnboardingResult:
    taste_id: str
    is_new: bool
    saved_favorites: list[str]
    skipped_favorites: list[str]
    profile: TasteProfile | None


def clean_platform(platform: str | None) -> str | None:
    """'Muse ' -> 'muse'. The platform name is only used for anonymous usage counts."""
    cleaned = normalize_tags([platform] if platform else [])
    return cleaned[0] if cleaned else None


def build_profile_changes(
    *,
    platform: str | None = None,
    home_city: str | None = None,
    neighborhoods: list[str] | None = None,
    dietary: list[str] | None = None,
    allergies: list[str] | None = None,
    liked_cuisines: list[str] | None = None,
    disliked_cuisines: list[str] | None = None,
    vibes: list[str] | None = None,
    budget: int | None = None,
    spice_level: int | None = None,
    notes: str | None = None,
    remove: list[str] | None = None,
) -> ProfileChanges:
    """Normalize raw agent input into one profile update."""
    removed = remove or []
    return ProfileChanges(
        platform=clean_platform(platform),
        home_city=home_city.strip() if home_city and home_city.strip() else None,
        neighborhoods=normalize_tags(neighborhoods),
        dietary=normalize_dietary(dietary),
        allergies=normalize_tags(allergies),
        liked_cuisines=normalize_cuisines(liked_cuisines),
        disliked_cuisines=normalize_cuisines(disliked_cuisines),
        vibes=normalize_tags(vibes),
        budget=budget,
        spice_level=spice_level,
        notes=scrub_text(notes, max_length=_MAX_NOTES_LENGTH),
        # A removed value can sit in any list, so match every normal form of it.
        remove=[
            *normalize_tags(removed),
            *normalize_dietary(removed),
            *normalize_cuisines(removed),
        ],
    )


def build_feedback_details(
    *,
    comment: str | None = None,
    visit_context: str | None = None,
    occasion: str | None = None,
    price_level: int | None = None,
    dishes: list[DishOpinion] | None = None,
    vibe_tags: list[str] | None = None,
    dietary_tags: list[str] | None = None,
    source: str = "conversation",
    platform: str | None = None,
) -> FeedbackDetails:
    """Normalize and scrub the optional signals of one opinion."""
    clean_dishes = []
    for dish in dishes or []:
        name = scrub_text(dish.name, max_length=_MAX_DISH_NAME_LENGTH)
        if name and dish.sentiment in _VALID_SENTIMENTS:
            clean_dishes.append(DishOpinion(name=name, sentiment=dish.sentiment))

    return FeedbackDetails(
        comment=scrub_text(comment),
        visit_context=scrub_text(visit_context, max_length=100),
        # Older agents only send visit_context. It carries the same signal.
        occasion=normalize_occasion(occasion or visit_context),
        price_level=price_level,
        dishes=clean_dishes,
        vibe_tags=normalize_tags(vibe_tags)[:5],
        dietary_tags=normalize_dietary(dietary_tags)[:5],
        source=source,
        platform=clean_platform(platform),
    )


async def record_feedback(
    *,
    place_name: str,
    city: str | None,
    sentiment: str,
    taste_id: str | None,
    details: FeedbackDetails,
    neighborhood: str | None = None,
    cuisine_tags: list[str] | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> FeedbackResult:
    """Resolve the place, then store one opinion about it."""
    if sentiment not in _VALID_SENTIMENTS:
        raise ValueError("Sentiment must be 'positive', 'negative', or 'neutral'.")

    if not city and taste_id:
        city = await profiles.get_home_city(taste_id)
    if not city:
        raise ValueError(NO_CITY_MESSAGE)

    place_id, _canonical_name = await find_or_create_place(
        name=place_name,
        city=city,
        neighborhood=neighborhood,
        cuisine_tags=cuisine_tags,
        address=scrub_text(address, max_length=200),
        latitude=latitude,
        longitude=longitude,
        hints=[dish.name for dish in details.dishes],
    )

    # The agent strips names and the regex scrub strips contact details.
    # When the comment check is on, Jev catches what both missed. A risky comment is dropped.
    if details.comment:
        risk = await decisions.comment_identifies_someone(details.comment)
        if risk is not None and risk >= get_settings().jev_comment_threshold:
            details.comment = None

    return await insert_feedback(
        place_id=place_id,
        sentiment=sentiment,
        taste_id=taste_id,
        details=details,
    )


async def onboard(
    *,
    taste_id: str | None,
    changes: ProfileChanges,
    favorites: list[FavoritePlace],
    dry_run: bool = False,
) -> OnboardingResult:
    """Start or refresh a person's profile in one call.

    Favorite places count as real positive opinions. They give the engine
    taste overlap with other people from the first minute.
    """
    is_new = taste_id is None
    taste_id = taste_id or mint_taste_id()
    favorites = favorites[:_MAX_FAVORITES]

    if dry_run:
        return OnboardingResult(
            taste_id=taste_id,
            is_new=is_new,
            saved_favorites=[],
            skipped_favorites=[favorite.name for favorite in favorites],
            profile=None,
        )

    await profiles.upsert_profile(taste_id, changes)

    saved: list[str] = []
    skipped: list[str] = []
    for favorite in favorites:
        try:
            result = await record_feedback(
                place_name=favorite.name,
                city=favorite.city or changes.home_city,
                sentiment="positive",
                taste_id=taste_id,
                details=build_feedback_details(source="onboarding", platform=changes.platform),
                neighborhood=favorite.neighborhood,
                cuisine_tags=favorite.cuisine_tags,
            )
            saved.append(result.place_name)
        except ValueError:
            skipped.append(favorite.name)

    return OnboardingResult(
        taste_id=taste_id,
        is_new=is_new,
        saved_favorites=saved,
        skipped_favorites=skipped,
        profile=await profiles.get_profile(taste_id),
    )


async def recommend(
    *,
    city: str | None,
    taste_id: str | None,
    cuisine: str | None = None,
    neighborhood: str | None = None,
    occasion: str | None = None,
    vibes: list[str] | None = None,
    max_price: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    similar_to: str | None = None,
    place_name: str | None = None,
    new_places_only: bool = False,
    friends_only: bool = False,
    limit: int = 5,
) -> SearchResult:
    """Rank places for one person and one request."""
    if not city and taste_id:
        city = await profiles.get_home_city(taste_id)
    if not city:
        return SearchResult(recommendations=[], message=NO_CITY_MESSAGE)

    taste = await profiles.load_taste_context(taste_id)
    result = await search_places(
        city,
        cuisine,
        neighborhood,
        limit,
        taste_id,
        taste=taste,
        occasion=normalize_occasion(occasion),
        vibes=normalize_tags(vibes),
        max_price=max_price,
        latitude=latitude,
        longitude=longitude,
        similar_to=similar_to,
        place_name=place_name,
        new_places_only=new_places_only,
        friends_only=friends_only,
    )

    # Some agents never read the server instructions, so the key rules ride along with the result.
    notes = []
    if result.recommendations:
        notes.append(ATTRIBUTION_NOTE)
    if not taste_id:
        notes.append(NO_PROFILE_NOTE)
    elif result.recommendations and not place_name:
        notes.append(FOLLOW_UP_NOTE)
    result.agent_note = " ".join(notes) or None
    return result
