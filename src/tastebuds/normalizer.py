import re

from tastebuds.taxonomy import cuisine_words


_SUFFIXES = {
    "restaurant",
    "cafe",
    "café",
    "bar",
    "grill",
    "eatery",
    "bistro",
    "pizzeria",
    "diner",
    "pub",
    "tavern",
    "shack",
    "spot",
}
_POSSESSIVE_SUFFIXES = ("'s", "\u2019s")
_PUNCTUATION_PATTERN = re.compile(r"[^\w\s-]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_STATE_SUFFIX_PATTERN = re.compile(r",\s*\w{2,}$")

_ADDRESS_PATTERN = re.compile(
    r"\b(on|at|off|near)\s+\w+\s+(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|way|ln|lane|ct|court)\b",
    re.IGNORECASE,
)

_ORDINAL_PATTERN = re.compile(
    r"\b(on|at)\s+\d+(st|nd|rd|th)\b",
    re.IGNORECASE,
)

# Nicknames people text. Only unambiguous ones belong here.
_CITY_ALIASES = {
    "sf": "san francisco",
    "san fran": "san francisco",
    "nyc": "new york",
    "new york city": "new york",
    "manhattan": "new york",
    "la": "los angeles",
    "sd": "san diego",
    "dc": "washington",
    "washington dc": "washington",
    "philly": "philadelphia",
    "vegas": "las vegas",
    "nola": "new orleans",
    "atl": "atlanta",
    "pdx": "portland",
    "slc": "salt lake city",
    "st louis": "saint louis",
    "st paul": "saint paul",
}

_DISH_NOISE = {"the", "a", "an", "their", "my", "some"}

# Words that point at a place without naming it. Keep this list tight:
# 'stand', 'house', and 'kitchen' are parts of real names such as "The Taco Stand".
_GENERIC_NAME_WORDS = {
    "the", "a", "an", "that", "this", "some", "my", "our", "new", "local", "good",
    "place", "places", "joint", "food", "near", "nearby", "me", "here", "around", "corner",
}


def _strip_trailing_suffixes(value: str) -> str:
    """Remove common restaurant suffixes from the end of a normalized name."""
    words = value.split()
    while words and words[-1] in _SUFFIXES:
        words.pop()

    return " ".join(words) if words else value


def normalize_name(name: str) -> str:
    """Normalize a restaurant name for deduplication.

    Pipeline: lowercase → strip possessives → remove punctuation →
    collapse whitespace → remove common suffixes → strip address fragments.
    """
    if not name:
        return ""

    normalized = name.lower()

    # Strip possessives
    for suffix in _POSSESSIVE_SUFFIXES:
        normalized = normalized.replace(suffix, "")

    # Remove punctuation except hyphens
    normalized = _PUNCTUATION_PATTERN.sub("", normalized)

    # Strip address fragments ("on 5th", "at main st")
    normalized = _ORDINAL_PATTERN.sub("", normalized)
    normalized = _ADDRESS_PATTERN.sub("", normalized)

    # Collapse whitespace
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized).strip()

    return _strip_trailing_suffixes(normalized)


def is_generic_name(name: str) -> bool:
    """True for 'that thai place' or 'a restaurant': words that name no specific place."""
    normalized = _PUNCTUATION_PATTERN.sub("", name.lower())
    words = normalized.split()
    if not words:
        return True

    generic = _SUFFIXES | _GENERIC_NAME_WORDS | cuisine_words()
    return all(word in generic for word in words)


_MIN_DISTINCTIVE_WORD_LENGTH = 4


def is_short_form(first: str, second: str) -> bool:
    """True when one normalized name is a short form of the other.

    People say "Nonna Pia" for "Nonna Pia Trattoria" and "Tajima" for "Tajima Ramen".
    Every word of the shorter name must appear in the longer one, and at least one of
    those words must be distinctive. "Thai" alone is not a short form of "Golden Lotus Thai".
    """
    first_words, second_words = set(first.split()), set(second.split())
    shorter, longer = sorted((first_words, second_words), key=len)
    if not shorter or not shorter <= longer:
        return False

    common = _SUFFIXES | _GENERIC_NAME_WORDS | cuisine_words()
    return any(
        len(word) >= _MIN_DISTINCTIVE_WORD_LENGTH and word not in common for word in shorter
    )


def normalize_city(city: str) -> str:
    """Normalize a city name: lowercase, strip state suffixes, resolve nicknames."""
    if not city:
        return ""

    normalized = city.lower().strip()

    # Strip state suffixes like ", CA" or ", California"
    normalized = _STATE_SUFFIX_PATTERN.sub("", normalized)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized.replace(".", "")).strip()

    return _CITY_ALIASES.get(normalized, normalized)


def normalize_dish(dish: str) -> str:
    """Normalize a dish name so 'The Spicy Miso Ramen!' and 'spicy miso ramen' match."""
    if not dish:
        return ""

    normalized = _PUNCTUATION_PATTERN.sub("", dish.lower())
    words = [word for word in normalized.split() if word not in _DISH_NOISE]
    return " ".join(words)
