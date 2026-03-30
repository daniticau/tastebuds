import re


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


def normalize_city(city: str) -> str:
    """Normalize a city name: lowercase, strip state suffixes."""
    if not city:
        return ""

    normalized = city.lower().strip()

    # Strip state suffixes like ", CA" or ", California"
    normalized = _STATE_SUFFIX_PATTERN.sub("", normalized)

    return normalized.strip()
