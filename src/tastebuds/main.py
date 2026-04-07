from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans

from tastebuds.db.client import close_db_pool, get_pool, init_db_pool
from tastebuds.server import mcp

logger = logging.getLogger(__name__)


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


mcp_app = mcp.http_app(path="/")

app = FastAPI(
    title="Tastebuds",
    version="0.1.0",
    lifespan=combine_lifespans(db_lifespan, mcp_app.lifespan),
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
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


app.mount("/mcp", mcp_app)
