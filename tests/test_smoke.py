import httpx
import pytest
from fastapi.testclient import TestClient

from tastebuds import main
from tastebuds.db import client as db_client
from tastebuds.main import app


@pytest.mark.anyio
async def test_health_endpoint_when_db_unavailable(monkeypatch):
    """Health returns 503 when the database cannot be reached."""
    async def failing_get_pool():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "get_pool", failing_get_pool)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"


@pytest.mark.anyio
async def test_get_pool_lazily_initializes(monkeypatch):
    class FakePool:
        async def close(self):
            return None

    fake_pool = FakePool()

    monkeypatch.setattr(db_client, "_pool", None)

    monkeypatch.setattr(
        db_client,
        "get_settings",
        lambda: type("Settings", (), {"database_url": "postgres://example"})(),
    )

    async def fake_create_pool(**kwargs):
        return fake_pool

    monkeypatch.setattr(db_client.asyncpg, "create_pool", fake_create_pool)

    pool = await db_client.get_pool()

    assert pool is fake_pool

    monkeypatch.setattr(db_client, "_pool", None)


def test_app_starts_when_db_init_fails(monkeypatch):
    async def failing_init_db_pool():
        raise RuntimeError("db unavailable during startup")

    async def failing_get_pool():
        raise RuntimeError("db still unavailable")

    monkeypatch.setattr(main, "init_db_pool", failing_init_db_pool)
    monkeypatch.setattr(main, "get_pool", failing_get_pool)

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
