import uuid

import pytest

from tastebud.db.client import close_db_pool, get_pool, init_db_pool
from tastebud.db.queries import (
    find_or_create_place,
    get_trending_places,
    insert_feedback,
    search_places,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def db_pool():
    """Initialize and tear down DB pool per test (each test has its own event loop)."""
    await init_db_pool()
    yield await get_pool()
    await close_db_pool()


@pytest.fixture()
async def test_place(db_pool):
    """Create a uniquely-named test place and clean it up after."""
    tag = uuid.uuid4().hex[:8]
    name = f"__test_place_{tag}"
    place_id, canonical = await find_or_create_place(
        name=name,
        city="san diego",
        neighborhood="test",
        cuisine_tags=["test"],
    )
    yield place_id, canonical

    # Cleanup: delete feedback then place
    await db_pool.execute("DELETE FROM feedback WHERE place_id = $1", place_id)
    await db_pool.execute("DELETE FROM places WHERE id = $1", place_id)


class TestSearch:
    async def test_search_returns_result(self):
        result = await search_places("san diego")
        assert hasattr(result, "recommendations")
        assert hasattr(result, "message")
        assert isinstance(result.recommendations, list)

    async def test_search_with_cuisine(self):
        result = await search_places("san diego", cuisine="thai")
        assert isinstance(result.recommendations, list)

    async def test_search_empty_city(self):
        result = await search_places("nonexistent_city_xyz")
        assert result.recommendations == []


class TestFeedback:
    async def test_feedback_round_trip(self, test_place):
        place_id, name = test_place
        result = await insert_feedback(
            place_id=place_id,
            sentiment="positive",
            comment="test feedback",
            visit_context="test",
        )
        assert result.success is True
        assert result.total_reviews >= 1

    async def test_feedback_updates_counts(self, test_place, db_pool):
        place_id, _ = test_place
        await insert_feedback(place_id=place_id, sentiment="positive")
        await insert_feedback(place_id=place_id, sentiment="negative")

        row = await db_pool.fetchrow(
            "SELECT positive_count, negative_count FROM places WHERE id = $1",
            place_id,
        )
        assert row["positive_count"] >= 1
        assert row["negative_count"] >= 1


class TestTrending:
    async def test_trending_returns_result(self):
        result = await get_trending_places("san diego")
        assert hasattr(result, "trending")
        assert hasattr(result, "period")
        assert isinstance(result.trending, list)
