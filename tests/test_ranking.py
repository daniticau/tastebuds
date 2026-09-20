import pytest

from tastebuds.ranking import (
    Candidate,
    QueryContext,
    RankingConfig,
    TasteContext,
    bayesian_quality,
    confidence_label,
    freshness,
    haversine_km,
    learned_cuisine_affinity,
    score_candidate,
)

CONFIG = RankingConfig()
NOBODY = TasteContext()
ANYTHING = QueryContext()


def _score(candidate, taste=NOBODY, query=ANYTHING):
    return score_candidate(candidate, taste, query, CONFIG)


class TestQuality:
    def test_one_rave_does_not_beat_a_proven_place(self):
        one_rave = Candidate(positive=1)
        proven = Candidate(positive=9, negative=1)
        assert _score(proven).value > _score(one_rave).value

    def test_no_opinions_sits_at_the_prior(self):
        assert bayesian_quality(0, 0, 0, CONFIG) == pytest.approx(CONFIG.prior_mean)

    def test_negatives_pull_below_the_prior(self):
        assert bayesian_quality(0, 0, 2, CONFIG) < CONFIG.prior_mean < bayesian_quality(2, 0, 0, CONFIG)

    def test_neutral_counts_as_half(self):
        assert bayesian_quality(0, 4, 0, CONFIG) == pytest.approx(
            bayesian_quality(2, 0, 2, CONFIG),
        )

    def test_more_agreement_ranks_higher(self):
        assert _score(Candidate(positive=20)).value > _score(Candidate(positive=5)).value

    def test_bad_place_ranks_below_unknown_place(self):
        assert _score(Candidate(negative=5)).value < _score(Candidate(positive=1)).value


class TestFreshness:
    def test_fresh_is_full_strength(self):
        assert freshness(0, CONFIG) == pytest.approx(1.0)

    def test_halflife(self):
        assert freshness(CONFIG.halflife_days, CONFIG) == pytest.approx(0.85)

    def test_old_praise_keeps_most_of_its_weight(self):
        assert freshness(5000, CONFIG) == pytest.approx(0.7, abs=0.001)

    def test_fresh_beats_stale_when_equal(self):
        fresh = Candidate(positive=5, days_since_feedback=3)
        stale = Candidate(positive=5, days_since_feedback=400)
        assert _score(fresh).value > _score(stale).value


class TestPersonalFit:
    def test_taste_neighbors_lift_a_place(self):
        liked_by_neighbors = Candidate(positive=3, neighbor_boost=0.4)
        plain = Candidate(positive=3)
        score = _score(liked_by_neighbors)
        assert score.value > _score(plain).value
        assert "people with similar taste liked it" in score.reasons

    def test_neighbor_boost_is_clamped(self):
        assert _score(Candidate(positive=3, neighbor_boost=50)).value == pytest.approx(
            _score(Candidate(positive=3, neighbor_boost=0.5)).value,
        )

    def test_neighbors_who_disliked_it_sink_a_place(self):
        assert _score(Candidate(positive=3, neighbor_boost=-0.3)).value < _score(
            Candidate(positive=3),
        ).value

    def test_a_close_friend_counts_more_than_a_distant_one(self):
        close = _score(Candidate(positive=3, friend_like_weight=2.0, friend_likes=1))
        distant = _score(Candidate(positive=3, friend_like_weight=0.5, friend_likes=1))
        nobody = _score(Candidate(positive=3))
        assert close.value > distant.value > nobody.value
        assert "someone close to them liked it" in close.reasons

    def test_a_friend_counts_more_than_a_stranger_with_similar_taste(self):
        friend = _score(Candidate(positive=3, friend_like_weight=1.0, friend_likes=1))
        circle = _score(Candidate(positive=3, circle_likes=1))
        assert friend.value > circle.value

    def test_friends_who_disliked_it_sink_a_place(self):
        warned = _score(Candidate(positive=3, friend_dislike_weight=2.0))
        assert warned.value < _score(Candidate(positive=3)).value
        assert warned.reasons == []

    def test_several_friends_are_counted_in_the_reason(self):
        score = _score(Candidate(positive=3, friend_like_weight=3.0, friend_likes=2))
        assert "2 people close to them liked it" in score.reasons

    def test_circle_likes_lift_a_place(self):
        score = _score(Candidate(positive=3, circle_likes=2))
        assert score.value > _score(Candidate(positive=3)).value
        assert "2 in their circle liked it" in score.reasons

    def test_circle_dislikes_sink_a_place(self):
        assert _score(Candidate(positive=3, circle_dislikes=2)).value < _score(
            Candidate(positive=3),
        ).value

    def test_disliked_cuisine_sinks_a_place(self):
        taste = TasteContext(disliked_cuisines=["seafood"])
        seafood = Candidate(positive=10, cuisine_tags=["seafood"])
        other = Candidate(positive=3, cuisine_tags=["thai"])
        assert _score(other, taste).value > _score(seafood, taste).value

    def test_disliked_cuisine_is_fine_when_asked_for(self):
        taste = TasteContext(disliked_cuisines=["seafood"])
        seafood = Candidate(positive=5, cuisine_tags=["seafood"])
        asked = QueryContext(cuisine_terms=["seafood"])
        assert _score(seafood, taste, asked).value > _score(seafood, taste).value

    def test_liked_cuisine_lifts_a_place(self):
        taste = TasteContext(liked_cuisines=["thai"])
        thai = Candidate(positive=3, cuisine_tags=["thai"])
        assert _score(thai, taste).value > _score(thai).value

    def test_learned_cuisine_affinity_counts(self):
        taste = TasteContext(learned_cuisines={"ramen": 0.6})
        ramen = Candidate(positive=3, cuisine_tags=["ramen"])
        score = _score(ramen, taste)
        assert score.value > _score(ramen).value
        assert "similar to places they enjoyed before" in score.reasons

    def test_dietary_match_lifts_a_place(self):
        taste = TasteContext(dietary=["vegetarian"])
        works = Candidate(positive=3, tags={"dietary": {"vegetarian": 2}})
        unknown = Candidate(positive=3)
        score = _score(works, taste)
        assert score.value > _score(unknown, taste).value
        assert "known to work for vegetarian" in score.reasons

    def test_occasion_match_lifts_a_place(self):
        query = QueryContext(occasion="date night")
        date_spot = Candidate(positive=4, tags={"occasion": {"date night": 3}})
        lunch_spot = Candidate(positive=4, tags={"occasion": {"quick lunch": 3}})
        assert _score(date_spot, NOBODY, query).value > _score(lunch_spot, NOBODY, query).value

    def test_neighborhood_match_ranks_first(self):
        query = QueryContext(neighborhood="north")
        here = Candidate(positive=2, neighborhood="North Park")
        elsewhere = Candidate(positive=4, neighborhood="La Jolla")
        assert _score(here, NOBODY, query).value > _score(elsewhere, NOBODY, query).value

    def test_too_expensive_is_penalized(self):
        taste = TasteContext(budget=1)
        cheap = Candidate(positive=3, price_level=1.0)
        fancy = Candidate(positive=3, price_level=4.0)
        assert _score(cheap, taste).value > _score(fancy, taste).value

    def test_similar_place_signal(self):
        score = _score(Candidate(positive=3, similar_likes=3))
        assert score.value > _score(Candidate(positive=3)).value

    def test_personal_fit_is_bounded(self):
        everything = Candidate(
            positive=3,
            neighbor_boost=0.5,
            circle_likes=50,
            similar_likes=50,
            cuisine_tags=["thai"],
            neighborhood="North Park",
            tags={"dietary": {"vegan": 9}, "occasion": {"date night": 9}, "vibe": {"cozy": 9}},
        )
        taste = TasteContext(dietary=["vegan"], liked_cuisines=["thai"], vibes=["cozy"])
        query = QueryContext(neighborhood="north park", occasion="date night")
        assert _score(everything, taste, query).value <= _score(Candidate(positive=3)).value * 2.0


class TestDistance:
    def test_haversine(self):
        # San Diego downtown to La Jolla is about 18 km.
        assert haversine_km(32.7157, -117.1611, 32.8328, -117.2713) == pytest.approx(16.6, abs=1.0)

    def test_near_beats_far(self):
        query = QueryContext(latitude=32.7157, longitude=-117.1611)
        near = Candidate(positive=3, latitude=32.7200, longitude=-117.1600)
        far = Candidate(positive=3, latitude=33.2000, longitude=-117.3000)
        near_score = _score(near, NOBODY, query)
        assert near_score.value > _score(far, NOBODY, query).value
        assert near_score.distance_km < 1
        assert "close by" in near_score.reasons

    def test_no_coordinates_means_no_distance(self):
        query = QueryContext(latitude=32.7, longitude=-117.1)
        assert _score(Candidate(positive=3), NOBODY, query).distance_km is None


class TestLearning:
    def test_one_good_night_is_a_weak_signal(self):
        affinity = learned_cuisine_affinity([(["ramen"], "positive")])
        assert affinity["ramen"] == pytest.approx(1 / 3)

    def test_repeated_love_is_a_strong_signal(self):
        affinity = learned_cuisine_affinity([(["ramen"], "positive")] * 6)
        assert affinity["ramen"] == pytest.approx(0.75)

    def test_mixed_history_cancels_out(self):
        affinity = learned_cuisine_affinity([(["thai"], "positive"), (["thai"], "negative")])
        assert affinity["thai"] == 0

    def test_confidence_labels(self):
        assert [confidence_label(n) for n in (0, 2, 3, 7, 8, 100)] == [
            "low", "low", "medium", "medium", "high", "high",
        ]
