"""Anonymous identity: taste tokens and circle invite codes.

A taste token links one person's opinions and profile. It holds no personal data.
The server mints it, so an agent never has to invent a UUID and remember it.
"""

import re
import secrets
from contextvars import ContextVar

from fastmcp.server.dependencies import get_http_headers

# Crockford base32 without i, l, o, u. An LLM copies these without mixing up look-alikes.
_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
_TOKEN_PREFIX = "tb_"
_TOKEN_BODY_LENGTH = 20
_INVITE_GROUP_LENGTH = 4

_TOKEN_RE = re.compile(rf"^{_TOKEN_PREFIX}[{_ALPHABET}]{{{_TOKEN_BODY_LENGTH}}}$")
# Tokens from before the server minted them: the agent made a UUID.
_LEGACY_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
)
_INVITE_RE = re.compile(rf"^[{_ALPHABET}]{{{_INVITE_GROUP_LENGTH * 2}}}$")
_FRIEND_INVITE_RE = re.compile(rf"^[{_ALPHABET}]{{{_INVITE_GROUP_LENGTH * 3}}}$")
_BEARER_RE = re.compile(r"^bearer\s+(\S+)$", re.IGNORECASE)

# The REST bridge sets this, because a plain HTTP call has no MCP request context.
request_bearer_token: ContextVar[str | None] = ContextVar("request_bearer_token", default=None)


def _random_string(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def mint_taste_id() -> str:
    """Create a new anonymous taste token (100 bits of randomness)."""
    return _TOKEN_PREFIX + _random_string(_TOKEN_BODY_LENGTH)


def sanitize_taste_id(taste_id: str | None) -> str | None:
    """Return the token in canonical form, or None when it is not a valid token."""
    if not taste_id:
        return None

    candidate = taste_id.strip().lower()
    if _TOKEN_RE.match(candidate) or _LEGACY_UUID_RE.match(candidate):
        return candidate
    return None


def parse_bearer(authorization: str | None) -> str | None:
    """Pull a valid taste token out of an Authorization header value."""
    if not authorization:
        return None

    match = _BEARER_RE.match(authorization.strip())
    return sanitize_taste_id(match.group(1)) if match else None


def resolve_taste_id(explicit: str | None = None) -> str | None:
    """Find who is calling: the explicit argument first, then the bearer token.

    An agent that stores the token as an API key never has to pass it as an argument.
    """
    token = sanitize_taste_id(explicit)
    if token:
        return token

    token = sanitize_taste_id(request_bearer_token.get())
    if token:
        return token

    headers = get_http_headers(include={"authorization"})
    return parse_bearer(headers.get("authorization"))


def mint_invite_code() -> str:
    """Create a circle invite code that is easy to text to a friend: 'k7m2-9xqd'."""
    return f"{_random_string(_INVITE_GROUP_LENGTH)}-{_random_string(_INVITE_GROUP_LENGTH)}"


def _compact_code(code: str | None) -> str:
    compact = re.sub(r"[\s-]", "", (code or "").strip().lower())
    # People read 'o' as zero and 'i' or 'l' as one.
    return compact.replace("o", "0").replace("i", "1").replace("l", "1")


def _grouped(compact: str) -> str:
    size = _INVITE_GROUP_LENGTH
    return "-".join(compact[start:start + size] for start in range(0, len(compact), size))


def sanitize_invite_code(code: str | None) -> str | None:
    """Return the circle invite code in canonical form, or None when it is malformed."""
    compact = _compact_code(code)
    return _grouped(compact) if _INVITE_RE.match(compact) else None


def mint_friend_invite_code() -> str:
    """Create a one-to-one friend invite code: 'k7m2-9xqd-4wte'. Three groups, 60 bits."""
    return _grouped(_random_string(_INVITE_GROUP_LENGTH * 3))


def sanitize_friend_invite_code(code: str | None) -> str | None:
    """Return the friend invite code in canonical form, or None when it is malformed."""
    compact = _compact_code(code)
    return _grouped(compact) if _FRIEND_INVITE_RE.match(compact) else None
