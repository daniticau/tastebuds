import re


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def sanitize_taste_id(taste_id: str | None) -> str | None:
    """Drop invalid taste tokens silently."""
    if taste_id is None:
        return None

    return taste_id if _UUID_RE.match(taste_id) else None
