import httpx
import pytest

from tastebuds.main import app


@pytest.mark.anyio
async def test_health_endpoint_without_db():
    """Health returns 503 when database pool is not initialized."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"
