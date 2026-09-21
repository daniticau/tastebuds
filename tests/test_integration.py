import uuid
from dataclasses import dataclass, field

import pytest

from tastebuds import decisions, service
from tastebuds.config import get_settings
from tastebuds.db import friends, profiles
from tastebuds.db.client import close_db_pool, get_pool, init_db_pool
from tastebuds.db.queries import (
    DishOpinion,
    FeedbackLimitError,
    find_or_create_place,
    get_trending_places,
    insert_feedback,
    search_places,
)
from tastebuds.identity import mint_taste_id
from tastebuds.normalizer import normalize_name

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def db_pool():
    """Initialize and tear down DB pool per test (each test has its own event loop)."""
    await init_db_pool()
    yield await get_pool()
    await close_db_pool()


@dataclass
class World:
    """One isolated city plus the people in it. Everything is deleted after the test."""

    city: str
    tokens: list[str] = field(default_factory=list)

    def person(self) -> str:
        token = mint_taste_id()
        self.tokens.append(token)
        return token

    async def opinion(self, token: str | None, place: str, sentiment: str = "positive", **details):
        return await service.record_feedback(
            place_name=place,
            city=self.city,
            sentiment=sentiment,
            taste_id=token,
            details=service.build_feedback_details(**details),
        )

    async def names(self, token: str | None = None, **kwargs) -> list[str]:
        result = await service.recommend(city=self.city, taste_id=token, **kwargs)
        return [place.name for place in result.recommendations]


@pytest.fixture()
async def world(db_pool):
    current = World(city=f"testville-{uuid.uuid4().hex[:10]}")
    yield current

    await db_pool.execute(
        "DELETE FROM feedback WHERE place_id IN (SELECT id FROM places WHERE city = $1)",
        current.city,
    )
    await db_pool.execute("DELETE FROM places WHERE city = $1", current.city)
    await db_pool.execute("DELETE FROM taste_profiles WHERE taste_id = ANY($1)", current.tokens)
    await db_pool.execute("DELETE FROM circle_members WHERE taste_id = ANY($1)", current.tokens)
    await db_pool.execute(
        "DELETE FROM friend_ties WHERE taste_id = ANY($1) OR friend_taste_id = ANY($1)",
        current.tokens,
    )
    await db_pool.execute("DELETE FROM friend_invites WHERE inviter_taste_id = ANY($1)", current.tokens)
    await db_pool.execute("DELETE FROM recommendation_events WHERE taste_id = ANY($1)", current.tokens)
    await db_pool.execute(
        "DELETE FROM circles c WHERE NOT EXISTS "
        "(SELECT 1 FROM circle_members cm WHERE cm.circle_id = c.id)",
    )


class TestPlaces:
    async def test_same_place_said_two_ways_is_one_place(self, world):
        first_id, first_name = await find_or_create_place(name="Joe's Pizza", city=world.city)
        second_id, second_name = await find_or_create_place(
            name="Joe Pizza Restaurant",
            city=world.city,
        )
        assert second_id == first_id
        assert second_name == first_name

    async def test_later_mentions_enrich_a_place(self, world, db_pool):
        place_id, _ = await find_or_create_place(name="Golden Lotus", city=world.city)
        await find_or_create_place(
            name="Golden Lotus",
            city=world.city,
            neighborhood="North Park",
            cuisine_tags=["pad thai", "Thai food"],
            address="123 Main St",
            latitude=32.75,
            longitude=-117.13,
        )
        row = await db_pool.fetchrow("SELECT * FROM places WHERE id = $1", place_id)
        assert row["neighborhood"] == "North Park"
        assert row["address"] == "123 Main St"
        assert row["latitude"] == pytest.approx(32.75)
        assert {"thai", "pad thai"} <= set(row["cuisine_tags"])

    async def test_a_short_form_finds_the_one_place_it_can_mean(self, world):
        full_id, _ = await find_or_create_place(name="Nonna Pia Trattoria", city=world.city)
        short_id, short_name = await find_or_create_place(name="nonna pia", city=world.city)
        assert (short_id, short_name) == (full_id, "Nonna Pia Trattoria")

    async def test_a_short_form_that_fits_two_places_is_not_guessed(self, world):
        first_id, _ = await find_or_create_place(name="Casa Oaxaca Centro Mercado", city=world.city)
        second_id, _ = await find_or_create_place(name="Casa Oaxaca Playa Hermosa", city=world.city)
        assert first_id != second_id
        third_id, _ = await find_or_create_place(name="Oaxaca", city=world.city)
        assert third_id not in (first_id, second_id)

    async def test_generic_name_is_rejected(self, world):
        with pytest.raises(ValueError):
            await find_or_create_place(name="restaurant", city=world.city)

    async def test_city_nickname_resolves(self, db_pool):
        place_id, _ = await find_or_create_place(name=f"Nickname Test {uuid.uuid4().hex[:8]}", city="SF")
        try:
            city = await db_pool.fetchval("SELECT city FROM places WHERE id = $1", place_id)
            assert city == "san francisco"
        finally:
            await db_pool.execute("DELETE FROM places WHERE id = $1", place_id)


class TestFeedback:
    async def test_feedback_updates_counts(self, world, db_pool):
        await world.opinion(world.person(), "Golden Lotus", "positive")
        await world.opinion(world.person(), "Golden Lotus", "negative")
        result = await world.opinion(None, "Golden Lotus", "neutral")

        assert result.total_reviews == 3
        row = await db_pool.fetchrow(
            "SELECT * FROM places WHERE city = $1 AND name_normalized = 'golden lotus'",
            world.city,
        )
        assert (row["positive_count"], row["negative_count"], row["neutral_count"]) == (1, 1, 1)
        assert row["avg_rating"] == pytest.approx(0.5)

    async def test_one_person_holds_one_opinion_per_place(self, world, db_pool):
        person = world.person()
        for _ in range(3):
            await world.opinion(person, "Golden Lotus", "positive")
        result = await world.opinion(person, "Golden Lotus", "negative")

        assert result.total_reviews == 1
        row = await db_pool.fetchrow(
            "SELECT positive_count, negative_count, avg_rating FROM places WHERE city = $1",
            world.city,
        )
        assert (row["positive_count"], row["negative_count"]) == (0, 1)
        assert row["avg_rating"] == pytest.approx(0.0)
        # The history stays. Only the vote is replaced.
        assert await db_pool.fetchval(
            "SELECT COUNT(*) FROM feedback WHERE taste_id = $1", person,
        ) == 4

    async def test_anonymous_opinions_always_count(self, world):
        await world.opinion(None, "Golden Lotus", "positive")
        result = await world.opinion(None, "Golden Lotus", "positive")
        assert result.total_reviews == 2

    async def test_dishes_tags_and_price_are_stored(self, world):
        await world.opinion(
            world.person(),
            "Sarku Japan",
            "positive",
            comment="Teriyaki was amazing but the rice was meh.",
            dishes=[DishOpinion("Teriyaki Chicken", "positive"), DishOpinion("the rice", "negative")],
            occasion="quick",
            price_level=1,
            vibe_tags=["casual"],
            dietary_tags=["GF"],
        )
        await world.opinion(
            world.person(),
            "Sarku Japan",
            "positive",
            dishes=[DishOpinion("teriyaki chicken!", "positive")],
            price_level=2,
        )

        result = await service.recommend(city=world.city, taste_id=None)
        place = result.recommendations[0]
        assert place.order_this == ["Teriyaki Chicken"]
        assert place.skip_this == ["the rice"]
        assert place.good_for == ["quick lunch"]
        assert place.vibes == ["casual"]
        assert place.dietary_fit == ["gluten-free"]
        assert place.price_level in (1, 2)
        assert place.notes == ["Teriyaki was amazing but the rice was meh."]

    async def test_daily_limit_per_person(self, world, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "max_feedback_per_token_per_day", 2)
        person = world.person()
        await world.opinion(person, "Golden Lotus")
        await world.opinion(person, "Smoky Oak Barbecue")
        with pytest.raises(FeedbackLimitError):
            await world.opinion(person, "Blue Harbor Sushi")

    async def test_bad_sentiment_is_rejected(self, world):
        with pytest.raises(ValueError):
            await world.opinion(None, "Golden Lotus", "amazing")

    async def test_feedback_without_city_uses_home_city(self, world):
        person = world.person()
        await profiles.upsert_profile(person, service.build_profile_changes(home_city=world.city))
        result = await service.record_feedback(
            place_name="Golden Lotus",
            city=None,
            sentiment="positive",
            taste_id=person,
            details=service.build_feedback_details(),
        )
        assert result.success
        assert await world.names() == ["Golden Lotus"]

    async def test_feedback_without_any_city_asks_for_one(self, world):
        with pytest.raises(ValueError, match="No city known"):
            await service.record_feedback(
                place_name="Golden Lotus",
                city=None,
                sentiment="positive",
                taste_id=None,
                details=service.build_feedback_details(),
            )


class TestSearch:
    async def test_empty_city(self, world):
        result = await service.recommend(city=world.city, taste_id=world.person())
        assert result.recommendations == []
        assert "own knowledge" in result.message
        # No picks from the engine, so nothing to credit.
        assert result.agent_note is None

    async def test_results_ask_for_a_short_credit(self, world):
        await world.opinion(world.person(), "Golden Lotus")

        personal = await service.recommend(city=world.city, taste_id=world.person())
        assert "Tastebuds recommends" in personal.agent_note
        assert "ask casually how it went" in personal.agent_note

        anonymous = await service.recommend(city=world.city, taste_id=None)
        assert "Tastebuds recommends" in anonymous.agent_note
        assert "start_taste_profile" in anonymous.agent_note

        trending = await get_trending_places(world.city)
        assert "Tastebuds recommends" not in trending.message  # one opinion is not a trend

    async def test_no_city_at_all(self):
        result = await service.recommend(city=None, taste_id=None)
        assert result.recommendations == []
        assert "No city known" in result.message

    async def test_proven_place_beats_single_rave(self, world):
        await world.opinion(world.person(), "Single Rave Cafe")
        for _ in range(6):
            await world.opinion(world.person(), "Proven Kitchen")
        await world.opinion(world.person(), "Proven Kitchen", "negative")

        assert await world.names() == ["Proven Kitchen", "Single Rave Cafe"]

    async def test_cuisine_search_uses_the_taxonomy(self, world):
        await find_or_create_place(name="Tajima", city=world.city, cuisine_tags=["ramen"])
        await find_or_create_place(name="Casa Verde", city=world.city, cuisine_tags=["tacos"])
        await world.opinion(world.person(), "Tajima")
        await world.opinion(world.person(), "Casa Verde")

        assert await world.names(cuisine="Japanese food") == ["Tajima"]
        assert await world.names(cuisine="ramen") == ["Tajima"]
        assert await world.names(cuisine="mexican") == ["Casa Verde"]
        assert await world.names(cuisine="ethiopian") == []

    async def test_neighborhood_ranks_first_but_does_not_hide_the_rest(self, world):
        await find_or_create_place(name="Parkside Noodles", city=world.city, neighborhood="North Park")
        await find_or_create_place(name="Harbor Grill House", city=world.city, neighborhood="La Jolla")
        await world.opinion(world.person(), "Parkside Noodles")
        for _ in range(3):
            await world.opinion(world.person(), "Harbor Grill House")

        assert await world.names() == ["Harbor Grill House", "Parkside Noodles"]
        assert await world.names(neighborhood="north") == ["Parkside Noodles", "Harbor Grill House"]

    async def test_disliked_places_never_come_back(self, world):
        me = world.person()
        await world.opinion(me, "Golden Lotus", "negative")
        await world.opinion(world.person(), "Golden Lotus")
        await world.opinion(world.person(), "Smoky Oak Barbecue")

        assert "Golden Lotus" in await world.names()
        assert await world.names(me) == ["Smoky Oak Barbecue"]

    async def test_new_places_only(self, world):
        me = world.person()
        await world.opinion(me, "Golden Lotus")
        await world.opinion(world.person(), "Smoky Oak Barbecue")

        assert set(await world.names(me)) == {"Golden Lotus", "Smoky Oak Barbecue"}
        assert await world.names(me, new_places_only=True) == ["Smoky Oak Barbecue"]

    async def test_own_history_is_reported(self, world):
        me = world.person()
        await world.opinion(me, "Golden Lotus")
        result = await service.recommend(city=world.city, taste_id=me)
        assert result.recommendations[0].your_history == "they loved it before"

    async def test_place_lookup_answers_even_about_a_disliked_place(self, world):
        me = world.person()
        await world.opinion(me, "Golden Lotus", "negative")
        await world.opinion(world.person(), "Smoky Oak Barbecue")

        result = await service.recommend(city=world.city, taste_id=me, place_name="golden lotus thai")
        assert [place.name for place in result.recommendations] == ["Golden Lotus"]
        assert result.recommendations[0].your_history == "they did not like it before"

    async def test_own_comment_is_not_echoed_back(self, world):
        me = world.person()
        await world.opinion(me, "Golden Lotus", comment="My own words.")
        await world.opinion(world.person(), "Golden Lotus", comment="Someone else's words.")

        result = await service.recommend(city=world.city, taste_id=me)
        assert result.recommendations[0].notes == ["Someone else's words."]


class TestPersonalization:
    async def test_taste_neighbors_change_the_ranking(self, world):
        me, twin, opposite = world.person(), world.person(), world.person()

        # The twin agrees with me on two places. The opposite disagrees on both.
        await world.opinion(me, "Golden Lotus", "positive")
        await world.opinion(twin, "Golden Lotus", "positive")
        await world.opinion(opposite, "Golden Lotus", "negative")
        await world.opinion(me, "Smoky Oak Barbecue", "negative")
        await world.opinion(twin, "Smoky Oak Barbecue", "negative")
        await world.opinion(opposite, "Smoky Oak Barbecue", "positive")

        # Two places I have not tried. Each has one fan.
        await world.opinion(twin, "Blue Harbor Sushi", "positive")
        await world.opinion(opposite, "Nonna Pia Trattoria", "positive")

        mine = await world.names(me, new_places_only=True)
        assert mine == ["Blue Harbor Sushi", "Nonna Pia Trattoria"]

        result = await service.recommend(city=world.city, taste_id=me, new_places_only=True)
        assert "people with similar taste liked it" in result.recommendations[0].why

        # For the opposite person the same two places rank the other way round.
        await world.opinion(world.person(), "Blue Harbor Sushi", "positive")
        await world.opinion(world.person(), "Nonna Pia Trattoria", "positive")
        theirs = await world.names(opposite, new_places_only=True)
        assert theirs[-1] == "Blue Harbor Sushi" or "Blue Harbor Sushi" not in theirs

    async def test_profile_shapes_the_ranking(self, world):
        await find_or_create_place(name="Blue Harbor", city=world.city, cuisine_tags=["seafood"])
        await find_or_create_place(name="Golden Lotus", city=world.city, cuisine_tags=["thai"])
        for _ in range(5):
            await world.opinion(world.person(), "Blue Harbor")
        await world.opinion(world.person(), "Golden Lotus")

        me = world.person()
        assert (await world.names(me))[0] == "Blue Harbor"

        await profiles.upsert_profile(
            me,
            service.build_profile_changes(liked_cuisines=["thai"], disliked_cuisines=["seafood"]),
        )
        assert (await world.names(me))[0] == "Golden Lotus"
        # They can still ask for seafood on purpose.
        assert await world.names(me, cuisine="seafood") == ["Blue Harbor"]

    async def test_dietary_fit_lifts_a_place(self, world):
        await world.opinion(world.person(), "Green Bowl Kitchen", dietary_tags=["vegetarian"])
        await world.opinion(world.person(), "Smoky Oak Barbecue")
        await world.opinion(world.person(), "Smoky Oak Barbecue")

        me = world.person()
        assert (await world.names(me))[0] == "Smoky Oak Barbecue"
        await profiles.upsert_profile(me, service.build_profile_changes(dietary=["veggie"]))
        assert (await world.names(me))[0] == "Green Bowl Kitchen"

    async def test_somewhere_like_a_place_i_name(self, world):
        fan_one, fan_two = world.person(), world.person()
        for fan in (fan_one, fan_two):
            await world.opinion(fan, "Tajima")
            await world.opinion(fan, "Menya Ultra")
        for _ in range(3):
            await world.opinion(world.person(), "Smoky Oak Barbecue")

        names = await world.names(similar_to="tajima")
        assert "Tajima" not in names
        assert names[0] == "Menya Ultra"

    async def test_learned_cuisines_show_in_profile(self, world):
        me = world.person()
        await find_or_create_place(name="Tajima", city=world.city, cuisine_tags=["ramen"])
        await find_or_create_place(name="Menya Ultra", city=world.city, cuisine_tags=["ramen"])
        await world.opinion(me, "Tajima")
        await world.opinion(me, "Menya Ultra")
        await world.opinion(me, "Smoky Oak Barbecue", "negative")

        profile = await profiles.get_profile(me)
        assert profile.exists is False
        assert profile.learned.opinion_count == 3
        assert "ramen" in profile.learned.top_cuisines
        assert set(profile.learned.loved_places) == {"Tajima", "Menya Ultra"}
        assert profile.learned.avoided_places == ["Smoky Oak Barbecue"]


class TestOnboarding:
    async def test_one_call_builds_the_profile_and_seeds_opinions(self, world):
        result = await service.onboard(
            taste_id=None,
            changes=service.build_profile_changes(
                platform="muse",
                home_city=world.city,
                dietary=["vegetarian"],
                allergies=["Peanuts"],
                liked_cuisines=["Thai food"],
            ),
            favorites=[
                service.FavoritePlace(name="Golden Lotus", cuisine_tags=["thai"]),
                service.FavoritePlace(name="restaurant"),
            ],
        )
        world.tokens.append(result.taste_id)

        assert result.is_new
        assert result.saved_favorites == ["Golden Lotus"]
        assert result.skipped_favorites == ["restaurant"]
        assert result.profile.dietary == ["vegetarian"]
        assert result.profile.allergies == ["peanuts"]
        assert result.profile.liked_cuisines == ["thai"]
        assert result.profile.learned.loved_places == ["Golden Lotus"]

        # The favorite is a real opinion: the next person in town can get it.
        assert await world.names() == ["Golden Lotus"]
        # Searching needs no city now.
        found = await service.recommend(city=None, taste_id=result.taste_id)
        assert [place.name for place in found.recommendations] == ["Golden Lotus"]

    async def test_dry_run_stores_nothing(self, world, db_pool):
        result = await service.onboard(
            taste_id=None,
            changes=service.build_profile_changes(home_city=world.city),
            favorites=[service.FavoritePlace(name="Golden Lotus")],
            dry_run=True,
        )
        assert result.saved_favorites == []
        assert await world.names() == []
        assert await db_pool.fetchval(
            "SELECT COUNT(*) FROM taste_profiles WHERE taste_id = $1", result.taste_id,
        ) == 0

    async def test_onboarding_again_keeps_the_same_person(self, world):
        first = await service.onboard(
            taste_id=None,
            changes=service.build_profile_changes(home_city=world.city, dietary=["halal"]),
            favorites=[],
        )
        world.tokens.append(first.taste_id)
        second = await service.onboard(
            taste_id=first.taste_id,
            changes=service.build_profile_changes(liked_cuisines=["thai"]),
            favorites=[],
        )
        assert second.taste_id == first.taste_id
        assert not second.is_new
        assert second.profile.dietary == ["halal"]
        assert second.profile.liked_cuisines == ["thai"]


class TestProfile:
    async def test_update_merges_and_removes(self, world):
        me = world.person()
        await profiles.upsert_profile(
            me,
            service.build_profile_changes(dietary=["vegetarian", "halal"], budget=2),
        )
        await profiles.upsert_profile(
            me,
            service.build_profile_changes(remove=["veggie"], vibes=["Cozy"], spice_level=3),
        )
        profile = await profiles.get_profile(me)
        assert profile.dietary == ["halal"]
        assert profile.vibes == ["cozy"]
        assert (profile.budget, profile.spice_level) == (2, 3)

    async def test_forget_me(self, world, db_pool):
        me = world.person()
        await profiles.upsert_profile(me, service.build_profile_changes(dietary=["vegan"]))
        await world.opinion(me, "Golden Lotus")
        await profiles.create_circle(me, "roommates")

        await profiles.delete_profile(me)

        profile = await profiles.get_profile(me)
        assert profile.exists is False
        assert profile.learned.opinion_count == 0
        assert profile.circles == []
        # The opinion still helps the crowd, with no link to anyone.
        assert await world.names() == ["Golden Lotus"]
        assert await db_pool.fetchval("SELECT COUNT(*) FROM feedback WHERE taste_id = $1", me) == 0


class TestCircles:
    async def test_circle_boosts_after_it_is_big_enough(self, world):
        me, friend_one, friend_two = world.person(), world.person(), world.person()
        await world.opinion(friend_one, "Nonna Pia Trattoria")
        for _ in range(2):
            await world.opinion(world.person(), "Smoky Oak Barbecue")
        assert (await world.names(me))[0] == "Smoky Oak Barbecue"

        circle = await profiles.create_circle(me, "roommates")
        assert circle.active is False
        joined = await profiles.join_circle(friend_one, circle.invite_code)
        assert (joined.member_count, joined.active) == (2, False)
        # Two members: the circle stays silent, or the signal would name the friend.
        assert (await world.names(me))[0] == "Smoky Oak Barbecue"

        joined = await profiles.join_circle(friend_two, circle.invite_code)
        assert (joined.member_count, joined.active) == (3, True)
        result = await service.recommend(city=world.city, taste_id=me)
        assert result.recommendations[0].name == "Nonna Pia Trattoria"
        assert "1 in their circle liked it" in result.recommendations[0].why

    async def test_join_is_idempotent_and_leave_works(self, world):
        me, friend = world.person(), world.person()
        circle = await profiles.create_circle(me, None)
        await profiles.join_circle(friend, circle.invite_code)
        again = await profiles.join_circle(friend, circle.invite_code)
        assert again.member_count == 2

        assert await profiles.leave_circle(friend, circle.invite_code) is True
        assert await profiles.leave_circle(friend, circle.invite_code) is False
        assert (await profiles.get_profile(friend)).circles == []

    async def test_last_member_leaving_removes_the_circle(self, world, db_pool):
        me = world.person()
        circle = await profiles.create_circle(me, None)
        await profiles.leave_circle(me, circle.invite_code)
        assert await db_pool.fetchval(
            "SELECT COUNT(*) FROM circles WHERE invite_code = $1", circle.invite_code,
        ) == 0

    async def test_unknown_code(self, world):
        with pytest.raises(profiles.CircleError):
            await profiles.join_circle(world.person(), "zzzz-zzzz")


class TestQuickDecisions:
    """Place matching with a stand-in for Jev. The real client is tested in test_decisions.py."""

    def _jev_says(self, monkeypatch, decision):
        calls = []

        async def fake_decide_place(**kwargs):
            calls.append(kwargs)
            return decision

        monkeypatch.setattr(decisions, "decide_place", fake_decide_place)
        return calls

    async def _similarity(self, db_pool, first: str, second: str) -> float:
        return await db_pool.fetchval(
            "SELECT similarity($1, $2)", normalize_name(first), normalize_name(second),
        )

    async def test_jev_merges_what_the_name_match_alone_would_split(self, world, db_pool, monkeypatch):
        # 0.54: under the fixed 0.6 rule these two would become two places.
        assert 0.25 < await self._similarity(db_pool, "Tajima", "Tajima Ramen") < 0.6
        known_id, _ = await find_or_create_place(name="Tajima", city=world.city, cuisine_tags=["ramen"])

        calls = self._jev_says(monkeypatch, decisions.PlaceDecision(answered_sameness=True, same_as=0))
        merged_id, merged_name = await find_or_create_place(
            name="Tajima Ramen", city=world.city, hints=["tonkotsu"],
        )

        assert (merged_id, merged_name) == (known_id, "Tajima")
        assert calls[0]["candidates"][0].name == "Tajima"
        assert calls[0]["hints"] == ["tonkotsu"]

    async def test_jev_splits_what_the_name_match_alone_would_merge(self, world, db_pool, monkeypatch):
        assert 0.6 < await self._similarity(db_pool, "Pho Hoa Noodle", "Pho Hoa Binh Noodle") < 0.85
        known_id, _ = await find_or_create_place(name="Pho Hoa Noodle", city=world.city)

        self._jev_says(monkeypatch, decisions.PlaceDecision(answered_sameness=True, same_as=None))
        other_id, _ = await find_or_create_place(name="Pho Hoa Binh Noodle", city=world.city)
        assert other_id != known_id

    async def test_without_an_answer_the_fixed_rule_decides(self, world, monkeypatch):
        known_id, _ = await find_or_create_place(name="Pho Hoa Noodle", city=world.city)
        self._jev_says(monkeypatch, None)
        same_id, _ = await find_or_create_place(name="Pho Hoa Binh Noodle", city=world.city)
        assert same_id == known_id

    async def test_a_strong_name_match_never_asks_jev(self, world, monkeypatch):
        known_id, _ = await find_or_create_place(name="Golden Lotus Thai", city=world.city)
        calls = self._jev_says(monkeypatch, decisions.PlaceDecision(answered_sameness=True, same_as=None))
        same_id, _ = await find_or_create_place(name="Golden Lotus Thai Restaurant", city=world.city)
        assert same_id == known_id
        assert calls == []

    async def test_jev_tags_a_new_place_that_came_without_a_cuisine(self, world, db_pool, monkeypatch):
        calls = self._jev_says(monkeypatch, decisions.PlaceDecision(cuisine="ramen"))
        place_id, _ = await find_or_create_place(name="Menya Ultra", city=world.city)

        tags = await db_pool.fetchval("SELECT cuisine_tags FROM places WHERE id = $1", place_id)
        assert set(tags) == {"ramen", "japanese", "noodles"}
        assert calls[0]["need_cuisine"] is True

    async def test_a_tagged_new_place_with_no_lookalikes_never_asks_jev(self, world, monkeypatch):
        calls = self._jev_says(monkeypatch, decisions.PlaceDecision(cuisine="thai"))
        await find_or_create_place(name="Menya Ultra", city=world.city, cuisine_tags=["ramen"])
        assert calls == []

    async def test_a_risky_comment_is_dropped_but_the_opinion_counts(self, world, db_pool, monkeypatch):
        async def risky(_comment):
            return 0.93

        monkeypatch.setattr(decisions, "comment_identifies_someone", risky)
        result = await world.opinion(world.person(), "Golden Lotus", comment="Sarah from Acme loved it.")

        assert result.total_reviews == 1
        assert await db_pool.fetchval(
            "SELECT comment FROM feedback f JOIN places p ON p.id = f.place_id WHERE p.city = $1",
            world.city,
        ) is None


class TestFriends:
    async def _link(self, me: str, friend: str, mine: int = 2, theirs: int = 2) -> str:
        code = await friends.create_invite(me, mine)
        await friends.accept_invite(friend, code, theirs)
        return code

    async def test_friends_shape_the_ranking_once_two_have_joined(self, world):
        me, best_friend, coworker = world.person(), world.person(), world.person()
        await world.opinion(best_friend, "Nonna Pia Trattoria")
        for _ in range(3):
            await world.opinion(world.person(), "Smoky Oak Barbecue")
        assert (await world.names(me))[0] == "Smoky Oak Barbecue"

        await self._link(me, best_friend, mine=3)
        # One friend: the signal stays off, or it would reveal what that friend said.
        assert (await world.names(me))[0] == "Smoky Oak Barbecue"
        assert (await profiles.get_profile(me)).friend_signals_active is False

        await self._link(me, coworker, mine=1)
        result = await service.recommend(city=world.city, taste_id=me)
        assert result.recommendations[0].name == "Nonna Pia Trattoria"
        assert "someone close to them liked it" in result.recommendations[0].why
        assert (await profiles.get_profile(me)).friend_signals_active is True

    async def test_closer_friends_count_more(self, world):
        me, close, distant = world.person(), world.person(), world.person()
        await world.opinion(close, "Nonna Pia Trattoria")
        await world.opinion(distant, "Blue Harbor Sushi")
        close_ref = await self._link(me, close, mine=3)
        distant_ref = await self._link(me, distant, mine=1)
        assert await world.names(me) == ["Nonna Pia Trattoria", "Blue Harbor Sushi"]

        # Messaging habits change: the agent swaps the closeness levels.
        assert await friends.set_closeness(me, close_ref, 1) is True
        assert await friends.set_closeness(me, distant_ref, 3) is True
        assert await world.names(me) == ["Blue Harbor Sushi", "Nonna Pia Trattoria"]

    async def test_each_side_keeps_its_own_closeness(self, world):
        me, friend = world.person(), world.person()
        await self._link(me, friend, mine=3, theirs=1)
        assert [f.closeness for f in (await profiles.get_profile(me)).friends] == [3]
        assert [f.closeness for f in (await profiles.get_profile(friend)).friends] == [1]

    async def test_a_friend_warning_sinks_a_place(self, world):
        me, friend_one, friend_two = world.person(), world.person(), world.person()
        for _ in range(2):
            await world.opinion(world.person(), "Smoky Oak Barbecue")
        await world.opinion(world.person(), "Golden Lotus")
        await world.opinion(friend_one, "Smoky Oak Barbecue", "negative")
        await self._link(me, friend_one, mine=3)
        await self._link(me, friend_two)
        assert (await world.names(me))[0] == "Golden Lotus"

    async def test_friends_only_search(self, world):
        me, friend_one, friend_two = world.person(), world.person(), world.person()
        await world.opinion(friend_one, "Nonna Pia Trattoria")
        await world.opinion(world.person(), "Smoky Oak Barbecue")
        await self._link(me, friend_one)
        await self._link(me, friend_two)
        assert await world.names(me, friends_only=True) == ["Nonna Pia Trattoria"]

    async def test_invite_rules(self, world, db_pool):
        me, friend, late = world.person(), world.person(), world.person()
        code = await friends.create_invite(me, 2)

        with pytest.raises(friends.FriendError, match="own invite"):
            await friends.accept_invite(me, code, 2)
        with pytest.raises(friends.FriendError, match="No invite"):
            await friends.accept_invite(friend, "zzzz-zzzz-zzzz", 2)

        await friends.accept_invite(friend, code, 2)
        with pytest.raises(friends.FriendError, match="already used"):
            await friends.accept_invite(late, code, 2)

        expired = await friends.create_invite(me, 2)
        await db_pool.execute(
            "UPDATE friend_invites SET expires_at = now() - INTERVAL '1 day' WHERE invite_code = $1",
            expired,
        )
        with pytest.raises(friends.FriendError, match="expired"):
            await friends.accept_invite(late, expired, 2)

    async def test_either_side_can_end_the_link(self, world):
        me, friend = world.person(), world.person()
        code = await self._link(me, friend)
        assert await friends.remove_friend(friend, code) is True
        assert (await profiles.get_profile(me)).friends == []
        assert (await profiles.get_profile(friend)).friends == []
        assert await friends.remove_friend(friend, code) is False

    async def test_forget_me_removes_the_links(self, world, db_pool):
        me, friend = world.person(), world.person()
        await self._link(me, friend)
        await friends.create_invite(me, 2)
        await profiles.delete_profile(me)
        assert (await profiles.get_profile(friend)).friends == []
        assert await db_pool.fetchval(
            "SELECT COUNT(*) FROM friend_invites WHERE inviter_taste_id = $1", me,
        ) == 0


class TestFollowUps:
    async def _age_events(self, db_pool, token: str, hours: int) -> None:
        await db_pool.execute(
            "UPDATE recommendation_events SET created_at = created_at - MAKE_INTERVAL(hours := $2) "
            "WHERE taste_id = $1",
            token,
            hours,
        )

    async def test_follow_up_appears_once(self, world, db_pool):
        me = world.person()
        await world.opinion(world.person(), "Golden Lotus")
        await world.names(me)

        assert (await profiles.get_follow_ups(me)).follow_ups == []  # too soon

        await self._age_events(db_pool, me, hours=30)
        due = await profiles.get_follow_ups(me)
        assert [item.place_name for item in due.follow_ups] == ["Golden Lotus"]
        assert due.follow_ups[0].recommended_days_ago == 1

        assert (await profiles.get_follow_ups(me)).follow_ups == []  # never nag

    async def test_feedback_resolves_the_follow_up(self, world, db_pool):
        me = world.person()
        await world.opinion(world.person(), "Golden Lotus")
        await world.names(me)
        await self._age_events(db_pool, me, hours=30)
        await world.opinion(me, "Golden Lotus", "positive")

        assert (await profiles.get_follow_ups(me)).follow_ups == []

    async def test_anonymous_search_tracks_nothing(self, world, db_pool):
        await world.opinion(world.person(), "Golden Lotus")
        before = await db_pool.fetchval("SELECT COUNT(*) FROM recommendation_events")
        await world.names()
        assert await db_pool.fetchval("SELECT COUNT(*) FROM recommendation_events") == before


class TestTrending:
    async def test_trending_needs_two_recent_opinions(self, world):
        await world.opinion(world.person(), "Golden Lotus")
        await world.opinion(world.person(), "Golden Lotus")
        await world.opinion(world.person(), "Smoky Oak Barbecue")

        result = await get_trending_places(world.city)
        assert [place.name for place in result.trending] == ["Golden Lotus"]
        assert result.period == "last 30 days"

    async def test_legacy_call_shape_still_works(self, world):
        place_id, _ = await find_or_create_place(name="Golden Lotus", city=world.city)
        result = await insert_feedback(
            place_id=place_id,
            sentiment="positive",
            comment="legacy comment",
            visit_context="dinner",
            taste_id="legacy-token",
        )
        assert result.success
        found = await search_places(world.city, taste_id="someone-else")
        assert found.recommendations[0].notes == ["legacy comment"]
