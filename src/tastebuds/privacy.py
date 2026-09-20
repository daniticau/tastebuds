"""Second line of defense for anonymity.

The agent strips identifying details before it calls a tool. This module removes
what slips through: emails, phone numbers, links, and @handles.
"""

import re

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)\(?\+?\d[\d\s().-]{7,}\d(?!\w)")
_HANDLE_RE = re.compile(r"(?<!\w)@\w{2,}")
_SPACE_RE = re.compile(r"\s+")


def scrub_text(value: str | None, max_length: int = 500) -> str | None:
    """Remove contact details from free text. Return None when nothing useful is left."""
    if not value:
        return None

    scrubbed = _EMAIL_RE.sub("", value)
    scrubbed = _URL_RE.sub("", scrubbed)
    scrubbed = _PHONE_RE.sub("", scrubbed)
    scrubbed = _HANDLE_RE.sub("", scrubbed)
    scrubbed = _SPACE_RE.sub(" ", scrubbed).strip(" ,;-")

    return scrubbed[:max_length].strip() or None
