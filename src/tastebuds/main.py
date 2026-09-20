from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastmcp.exceptions import NotFoundError
from fastmcp.utilities.lifespan import combine_lifespans
from pydantic import ValidationError
from starlette.types import ASGIApp, Receive, Scope, Send

from tastebuds import decisions
from tastebuds.config import get_settings, public_base_url
from tastebuds.db.client import close_db_pool, get_pool, init_db_pool
from tastebuds.identity import parse_bearer, request_bearer_token
from tastebuds.playbook import connect_messages, llms_txt
from tastebuds.ratelimit import RateLimitMiddleware
from tastebuds.server import mcp

logger = logging.getLogger(__name__)

_LANDING_TEMPLATE = (Path(__file__).parent / "web" / "landing.html").read_text(encoding="utf-8")
_MAX_API_BODY_BYTES = 64_000
_API_PREFIX = "/api/v1"
_VERSION = "0.2.0"


@asynccontextmanager
async def db_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage database connection pool lifecycle."""
    try:
        await init_db_pool()
    except Exception:
        logger.exception(
            "Database pool initialization failed during startup; continuing in degraded mode",
        )
    yield
    await close_db_pool()
    await decisions.close_client()


class McpTrailingSlashMiddleware:
    """Serve /mcp/ and /mcp alike. Some MCP clients do not follow a redirect on POST."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp/":
            scope = {**scope, "path": "/mcp", "raw_path": b"/mcp"}
        await self.app(scope, receive, send)


def _rate_limit_settings() -> tuple[int, bool]:
    try:
        settings = get_settings()
    except ValidationError:
        return 300, True
    return settings.rate_limit_per_minute, settings.trust_proxy_headers


router = APIRouter()


@router.get("/health")
async def health():
    """Health check endpoint for monitoring."""
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        return {"status": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded"},
        )


@router.get("/", response_class=HTMLResponse)
async def landing() -> str:
    """One page for people: pick your assistant, copy one message, send it."""
    messages = json.dumps(connect_messages(public_base_url())).replace("</", "<\\/")
    return _LANDING_TEMPLATE.replace("__MESSAGES_JSON__", messages)


@router.get("/llms.txt", response_class=PlainTextResponse)
async def llms() -> str:
    """One page for agents that arrive with a browser instead of an MCP client."""
    return llms_txt(public_base_url())


@router.get("/openapi.json")
async def openapi() -> dict:
    """OpenAPI document for the REST bridge, built from the MCP tool schemas."""
    paths = {}
    for tool in await mcp.list_tools():
        description = tool.description or ""
        paths[f"{_API_PREFIX}/{tool.name}"] = {
            "post": {
                "operationId": tool.name,
                "summary": description.split("\n", 1)[0],
                "description": description,
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": tool.parameters}},
                },
                "responses": {
                    "200": {
                        "description": "Tool result",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "404": {"description": "Unknown tool"},
                    "422": {"description": "Invalid arguments"},
                },
                "security": [{}, {"tasteToken": []}],
            },
        }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Tastebuds",
            "version": _VERSION,
            "description": (
                "Food memory and crowd-taught restaurant recommendations for AI agents. "
                f"Read {public_base_url()}/llms.txt for the playbook."
            ),
        },
        "servers": [{"url": public_base_url()}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "tasteToken": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Optional. The taste_id from start_taste_profile.",
                },
            },
        },
    }


@router.post(_API_PREFIX + "/{tool_name}")
async def call_tool(tool_name: str, request: Request) -> JSONResponse:
    """REST bridge: run an MCP tool from a plain HTTP call. Same tools, same validation."""
    body = await request.body()
    if len(body) > _MAX_API_BODY_BYTES:
        return JSONResponse(status_code=413, content={"error": "Request body is too large."})

    try:
        arguments = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "The body must be JSON."})
    if not isinstance(arguments, dict):
        return JSONResponse(status_code=400, content={"error": "The body must be a JSON object."})

    reset = request_bearer_token.set(parse_bearer(request.headers.get("authorization")))
    try:
        result = await mcp.call_tool(tool_name, arguments)
    except NotFoundError:
        return JSONResponse(status_code=404, content={"error": f"Unknown tool: {tool_name}"})
    except ValidationError as exc:
        problems = [
            {"field": ".".join(str(part) for part in error["loc"]), "problem": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "Invalid arguments.", "problems": problems},
        )
    finally:
        request_bearer_token.reset(reset)

    return JSONResponse(content=result.structured_content or {})


def create_app() -> FastAPI:
    """Build the app. The MCP session manager runs once per instance, so tests build their own."""
    mcp_app = mcp.http_app(path="/mcp")
    application = FastAPI(
        title="Tastebuds",
        version=_VERSION,
        lifespan=combine_lifespans(db_lifespan, mcp_app.lifespan),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    per_minute, trust_proxy = _rate_limit_settings()
    application.add_middleware(
        RateLimitMiddleware,
        per_minute=per_minute,
        trust_proxy_headers=trust_proxy,
    )
    application.add_middleware(McpTrailingSlashMiddleware)

    application.include_router(router)
    # Last, so every route above wins. The MCP app answers /mcp.
    application.mount("/", mcp_app)
    return application


app = create_app()
