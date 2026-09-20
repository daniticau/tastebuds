"""Shared vocabulary: cuisines, dietary needs, occasions, and vibes.

Agents send free text. This module maps it to a small stable vocabulary,
so "veggie", "Vegetarian" and "vegetarian-friendly" all land on one tag.
"""

import re
from functools import lru_cache

_CLEAN_RE = re.compile(r"[^\w&' -]")
_SPACE_RE = re.compile(r"\s+")
_MAX_TAG_LENGTH = 40

# Words that carry no meaning in a cuisine tag: "mexican food" -> "mexican".
_CUISINE_NOISE = {"food", "cuisine", "restaurant", "restaurants", "place", "places", "spot", "spots"}

_CUISINE_SYNONYMS = {
    "burger": "burgers",
    "hamburger": "burgers",
    "hamburgers": "burgers",
    "taco": "tacos",
    "burrito": "burritos",
    "dumpling": "dumplings",
    "noodle": "noodles",
    "sandwich": "sandwiches",
    "sub": "sandwiches",
    "subs": "sandwiches",
    "bagel": "bagels",
    "donut": "donuts",
    "doughnut": "donuts",
    "doughnuts": "donuts",
    "wing": "wings",
    "barbecue": "bbq",
    "barbeque": "bbq",
    "korean barbecue": "korean bbq",
    "kbbq": "korean bbq",
    "hotpot": "hot pot",
    "bubble tea": "boba",
    "milk tea": "boba",
    "espresso": "coffee",
    "cafe": "coffee",
    "café": "coffee",
    "coffee shop": "coffee",
    "desserts": "dessert",
    "sweets": "dessert",
    "gelato": "ice cream",
    "steak": "steakhouse",
    "steaks": "steakhouse",
    "dimsum": "dim sum",
    "yum cha": "dim sum",
    "med": "mediterranean",
    "viet": "vietnamese",
    "banh mi": "bánh mì",
    "poke bowl": "poke",
}

# Child -> parents. A ramen shop is also a japanese place and a noodles place.
_CUISINE_PARENTS = {
    "ramen": ("japanese", "noodles"),
    "sushi": ("japanese",),
    "izakaya": ("japanese",),
    "udon": ("japanese", "noodles"),
    "teriyaki": ("japanese",),
    "omakase": ("japanese", "sushi"),
    "tacos": ("mexican",),
    "burritos": ("mexican",),
    "birria": ("mexican",),
    "pho": ("vietnamese", "noodles"),
    "bánh mì": ("vietnamese", "sandwiches"),
    "dim sum": ("chinese",),
    "dumplings": ("chinese",),
    "hot pot": ("chinese",),
    "szechuan": ("chinese",),
    "sichuan": ("chinese",),
    "cantonese": ("chinese",),
    "korean bbq": ("korean", "bbq"),
    "korean fried chicken": ("korean", "chicken"),
    "pizza": ("italian",),
    "pasta": ("italian",),
    "curry": ("indian",),
    "biryani": ("indian",),
    "falafel": ("mediterranean",),
    "shawarma": ("mediterranean", "middle eastern"),
    "kebab": ("mediterranean", "middle eastern"),
    "lebanese": ("mediterranean", "middle eastern"),
    "greek": ("mediterranean",),
    "burgers": ("american",),
    "wings": ("american", "chicken"),
    "fried chicken": ("american", "chicken"),
    "diner": ("american",),
    "bagels": ("bakery", "breakfast"),
    "donuts": ("bakery", "dessert"),
    "ice cream": ("dessert",),
    "boba": ("tea", "dessert"),
    "poke": ("hawaiian", "seafood"),
    "oysters": ("seafood",),
    "brunch": ("breakfast",),
}

_DIETARY_SYNONYMS = {
    "veggie": "vegetarian",
    "vegetarian-friendly": "vegetarian",
    "vegetarian friendly": "vegetarian",
    "vegetarian options": "vegetarian",
    "no meat": "vegetarian",
    "plant-based": "vegan",
    "plant based": "vegan",
    "vegan-friendly": "vegan",
    "vegan friendly": "vegan",
    "vegan options": "vegan",
    "gf": "gluten-free",
    "gluten free": "gluten-free",
    "gluten-free options": "gluten-free",
    "celiac": "gluten-free",
    "coeliac": "gluten-free",
    "no gluten": "gluten-free",
    "dairy free": "dairy-free",
    "no dairy": "dairy-free",
    "lactose intolerant": "dairy-free",
    "lactose-free": "dairy-free",
    "nut free": "nut-free",
    "no nuts": "nut-free",
    "pescetarian": "pescatarian",
    "low carb": "low-carb",
    "no pork": "pork-free",
    "no beef": "beef-free",
    "no shellfish": "shellfish-free",
}

_OCCASION_SYNONYMS = {
    "date": "date night",
    "date-night": "date night",
    "romantic": "date night",
    "anniversary": "date night",
    "quick bite": "quick lunch",
    "quick": "quick lunch",
    "work lunch": "quick lunch",
    "grab and go": "quick lunch",
    "friends": "group",
    "groups": "group",
    "big group": "group",
    "party": "group",
    "birthday": "celebration",
    "special occasion": "celebration",
    "kids": "family",
    "family dinner": "family",
    "with kids": "family",
    "alone": "solo",
    "by myself": "solo",
    "take out": "takeout",
    "take-out": "takeout",
    "to go": "takeout",
    "to-go": "takeout",
    "pickup": "takeout",
    "drinks": "drinks",
    "happy hour": "drinks",
    "late": "late night",
    "late-night": "late night",
    "client dinner": "business",
    "work dinner": "business",
    "meeting": "business",
    "study": "work session",
    "laptop": "work session",
    "working": "work session",
}


_COMMON_CUISINES = {
    "american", "chinese", "japanese", "korean", "thai", "vietnamese", "indian", "mexican",
    "italian", "french", "spanish", "greek", "turkish", "lebanese", "ethiopian", "peruvian",
    "brazilian", "cuban", "caribbean", "filipino", "hawaiian", "german", "mediterranean",
    "asian", "fusion", "vegan", "vegetarian", "seafood", "breakfast", "lunch", "dinner",
}


@lru_cache
def cuisine_words() -> frozenset[str]:
    """Every single word the vocabulary knows as a cuisine or food type."""
    phrases = {*_COMMON_CUISINES, *_CUISINE_SYNONYMS, *_CUISINE_SYNONYMS.values(), *_CUISINE_PARENTS}
    for parents in _CUISINE_PARENTS.values():
        phrases.update(parents)
    return frozenset(word for phrase in phrases for word in phrase.split())


def _clean(value: str) -> str:
    cleaned = _CLEAN_RE.sub("", value.lower().replace("_", " "))
    return _SPACE_RE.sub(" ", cleaned).strip()[:_MAX_TAG_LENGTH].strip()


def normalize_cuisine(value: str) -> str:
    """Map free text to one cuisine tag: 'Mexican food' -> 'mexican', 'Burger' -> 'burgers'."""
    cleaned = _clean(value)
    if cleaned in _CUISINE_SYNONYMS:
        return _CUISINE_SYNONYMS[cleaned]

    words = [word for word in cleaned.split() if word not in _CUISINE_NOISE]
    stripped = " ".join(words)
    return _CUISINE_SYNONYMS.get(stripped, stripped)


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen.setdefault(value)
    return list(seen)


def normalize_cuisines(values: list[str] | None) -> list[str]:
    """Normalize a list of cuisine tags, in order, without duplicates."""
    return _dedupe([normalize_cuisine(value) for value in values or []])


def cuisine_tags_for_place(values: list[str] | None) -> list[str]:
    """Tags to store on a place: each tag plus its parents, so broad searches find it."""
    tags = normalize_cuisines(values)
    expanded = list(tags)
    for tag in tags:
        expanded.extend(_CUISINE_PARENTS.get(tag, ()))
    return _dedupe(expanded)


# Meal and style words say little about a place when they appear in its name.
_NOT_INFERRED_FROM_NAMES = {"breakfast", "lunch", "dinner", "fusion", "asian", "tea", "chicken"}


@lru_cache
def cuisine_choices() -> tuple[str, ...]:
    """Every cuisine tag the vocabulary can assign to a place, in a stable order."""
    known = {*_COMMON_CUISINES, *_CUISINE_PARENTS, *_CUISINE_SYNONYMS.values()}
    for parents in _CUISINE_PARENTS.values():
        known.update(parents)
    return tuple(sorted(known - _NOT_INFERRED_FROM_NAMES))


def infer_cuisines_from_name(place_name: str) -> list[str]:
    """Read cuisine tags out of a place name: 'Tajima Ramen' -> ['ramen'].

    Agents often log a place without cuisine tags. The name is the cheapest hint.
    """
    words = _clean(place_name).replace("'", "").split()
    phrases = [*words, *(" ".join(pair) for pair in zip(words, words[1:]))]

    known = cuisine_choices()
    found = []
    for phrase in phrases:
        cuisine = _CUISINE_SYNONYMS.get(phrase, phrase)
        if cuisine in known:
            found.append(cuisine)
    return _dedupe(found)


def cuisine_search_terms(value: str) -> list[str]:
    """Tags that satisfy a search: the cuisine itself plus every child of it.

    A search for 'japanese' also finds a place that people only tagged 'ramen'.
    A search for 'ramen' does not return every japanese place.
    """
    cuisine = normalize_cuisine(value)
    if not cuisine:
        return []

    children = [child for child, parents in _CUISINE_PARENTS.items() if cuisine in parents]
    return _dedupe([cuisine, *children])


def normalize_dietary(values: list[str] | None) -> list[str]:
    cleaned = [_clean(value) for value in values or []]
    return _dedupe([_DIETARY_SYNONYMS.get(value, value) for value in cleaned])


def normalize_occasion(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _clean(value)
    return _OCCASION_SYNONYMS.get(cleaned, cleaned) or None


def normalize_tags(values: list[str] | None) -> list[str]:
    """Generic tag cleanup for vibes, allergies, and neighborhoods."""
    return _dedupe([_clean(value) for value in values or []])
