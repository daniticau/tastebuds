"""Shared parameter types and error handling for the MCP tools."""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, Field, ValidationError

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong. Please try again."
NEEDS_TASTE_ID = (
    "This tool needs a taste_id. Call start_taste_profile once for this person, "
    "save the taste_id it returns, and pass it here."
)

TasteId = Annotated[
    str | None,
    Field(
        description=(
            "The person's anonymous taste token from start_taste_profile. "
            "Pass it on every call for personal results."
        ),
        max_length=40,
    ),
]
RequiredCity = Annotated[
    str,
    Field(description="City name, for example 'San Diego'.", max_length=100),
]
OptionalCity = Annotated[
    str | None,
    Field(
        description=(
            "City name, for example 'San Diego'. Infer it from the conversation. "
            "Leave empty to use the person's home city."
        ),
        max_length=100,
    ),
]
PriceLevel = Annotated[
    int | None,
    Field(description="Price from 1 (cheap) to 4 (splurge).", ge=1, le=4),
]
Latitude = Annotated[float | None, Field(description="Latitude, when known.", ge=-90, le=90)]
Longitude = Annotated[float | None, Field(description="Longitude, when known.", ge=-180, le=180)]


def as_list(value: object) -> object:
    """Forgive the two most common agent mistakes: one item instead of a list, and 'a, b' text."""
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, dict):
        return [value]
    return value


def named(value: object) -> object:
    """Let an agent send 'Tajima Ramen' where the schema asks for {'name': 'Tajima Ramen'}."""
    return {"name": value} if isinstance(value, str) else value


ShortTagList = Annotated[list[str] | None, BeforeValidator(as_list), Field(max_length=10)]

# Platforms read these hints to decide when to ask the person before a call.
# Accurate hints keep silent logging silent, and keep a confirmation on the one call that needs it.
READS = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False,
)
DELETES = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False,
)


def safe_tool[**P](fn: Callable[P, Awaitable[dict]]) -> Callable[P, Awaitable[dict]]:
    """Turn any failure into a short message the agent can act on. Never leak internals."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict:
        try:
            return await fn(*args, **kwargs)
        except ValidationError:
            # A pydantic error is a ValueError too, but its text quotes raw input.
            logger.exception("%s failed validation", fn.__name__)
            return {"success": False, "error": GENERIC_ERROR, "message": GENERIC_ERROR}
        except ValueError as exc:
            # The engine raises ValueError with text written for the agent.
            return {"success": False, "message": str(exc)}
        except Exception:
            logger.exception("%s failed", fn.__name__)
            return {"success": False, "error": GENERIC_ERROR, "message": GENERIC_ERROR}

    return wrapper
