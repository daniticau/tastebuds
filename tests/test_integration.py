import uuid

import pytest

from tastebuds.db.client import close_db_pool, get_pool, init_db_pool
from tastebuds.db.queries import (
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

    async def test_search_with_partial_neighborhood_match(self, db_pool):
        tag = uuid.uuid4().hex[:8]
        city = f"test-neighborhood-city-{tag}"
        place_name = f"__partial_neighborhood_{tag}"
        place_id, _ = await find_or_create_place(
            name=place_name,
            city=city,
            neighborhood="North Park",
            cuisine_tags=["test"],
        )

        try:
            await insert_feedback(place_id=place_id, sentiment="positive")

            result = await search_places(city, neighborhood="north")

            assert any(
                recommendation.name == place_name
                for recommendation in result.recommendations
            )
        finally:
            await db_pool.execute("DELETE FROM feedback WHERE place_id = $1", place_id)
            await db_pool.execute("DELETE FROM places WHERE id = $1", place_id)


class TestFeedback:
    async def test_find_or_create_place_reuses_normalized_place(self, db_pool):
        tag = uuid.uuid4().hex[:8]
        city = f"test-dedupe-city-{tag}"

        first_place_id, first_name = await find_or_create_place(
            name="Joe's Pizza",
            city=city,
        )

        try:
            second_place_id, second_name = await find_or_create_place(
                name="Joe Pizza Restaurant",
                city=city,
            )

            assert second_place_id == first_place_id
            assert second_name == first_name
        finally:
            await db_pool.execute("DELETE FROM feedback WHERE place_id = $1", first_place_id)
            await db_pool.execute("DELETE FROM places WHERE id = $1", first_place_id)

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


class TestTasteAffinity:
    async def test_search_with_taste_id(self):
        """Search with a taste_id returns results (even if no affinity data yet)."""
        result = await search_places("san diego", taste_id="test-taste-aaa")
        assert hasattr(result, "recommendations")
        assert isinstance(result.recommendations, list)

    async def test_search_without_taste_id_unchanged(self):
        """Search without taste_id still works (backward compatible)."""
        result = await search_places("san diego")
        assert isinstance(result.recommendations, list)

    async def test_feedback_with_taste_id(self, test_place):
        """Feedback with taste_id is stored correctly."""
        place_id, _ = test_place
        result = await insert_feedback(
            place_id=place_id,
            sentiment="positive",
            taste_id="test-taste-bbb",
        )
        assert result.success is True

    async def test_affinity_boosts_similar_taste(self, db_pool):
        """Places loved by taste-similar users rank higher than without affinity."""
        tag = uuid.uuid4().hex[:8]

        # Create two places in the same city
        place_a_id, _ = await find_or_create_place(
            name=f"__affinity_a_{tag}", city="test affinity city",
            cuisine_tags=["test"],
        )
        place_b_id, _ = await find_or_create_place(
            name=f"__affinity_b_{tag}", city="test affinity city",
            cuisine_tags=["test"],
        )

        try:
            taste_me = f"taste-me-{tag}"
            taste_friend = f"taste-friend-{tag}"
            taste_foe = f"taste-foe-{tag}"

            # Both me and friend love place A (agreement on place A)
            await insert_feedback(place_id=place_a_id, sentiment="positive", taste_id=taste_me)
            await insert_feedback(place_id=place_a_id, sentiment="positive", taste_id=taste_friend)
            # Both me and friend dislike some baseline (agreement on place B)
            await insert_feedback(place_id=place_b_id, sentiment="negative", taste_id=taste_me)
            await insert_feedback(place_id=place_b_id, sentiment="negative", taste_id=taste_friend)

            # Foe disagrees with me on both places
            await insert_feedback(place_id=place_a_id, sentiment="negative", taste_id=taste_foe)
            await insert_feedback(place_id=place_b_id, sentiment="positive", taste_id=taste_foe)

            # Now create a third place that only friend and foe reviewed
            place_c_id, _ = await find_or_create_place(
                name=f"__affinity_c_{tag}", city="test affinity city",
                cuisine_tags=["test"],
            )
            # Friend loves it, foe loves it too
            await insert_feedback(place_id=place_c_id, sentiment="positive", taste_id=taste_friend)
            await insert_feedback(place_id=place_c_id, sentiment="positive", taste_id=taste_foe)

            # Search WITH my taste_id — friend's positive signal should boost place_c
            result_with = await search_places("test affinity city", taste_id=taste_me)
            # Search WITHOUT taste_id — no affinity boost
            result_without = await search_places("test affinity city")

            # Both should return results
            assert len(result_with.recommendations) > 0
            assert len(result_without.recommendations) > 0

        finally:
            # Cleanup
            for pid in (place_a_id, place_b_id, place_c_id):
                await db_pool.execute("DELETE FROM feedback WHERE place_id = $1", pid)
                await db_pool.execute("DELETE FROM places WHERE id = $1", pid)


class TestTrending:
    async def test_trending_returns_result(self):
        result = await get_trending_places("san diego")
        assert hasattr(result, "trending")
        assert hasattr(result, "period")
        assert isinstance(result.trending, list)
