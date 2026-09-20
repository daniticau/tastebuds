from tastebuds.db.profiles import ProfileChanges, apply_changes, merge_list
from tastebuds.service import build_feedback_details, build_profile_changes
from tastebuds.db.queries import DishOpinion

_EMPTY = {
    "platform": None,
    "home_city": None,
    "home_city_display": None,
    "neighborhoods": [],
    "dietary": [],
    "allergies": [],
    "liked_cuisines": [],
    "disliked_cuisines": [],
    "vibes": [],
    "budget": None,
    "spice_level": None,
    "notes": None,
}


class TestMerge:
    def test_lists_merge_without_duplicates(self):
        assert merge_list(["thai"], ["ramen", "thai"], []) == ["thai", "ramen"]

    def test_remove_wins(self):
        assert merge_list(["thai", "ramen"], ["sushi"], ["ramen"]) == ["thai", "sushi"]

    def test_list_size_is_capped(self):
        assert len(merge_list([], [f"tag{i}" for i in range(100)], [])) == 25

    def test_update_keeps_what_was_not_mentioned(self):
        current = {**_EMPTY, "dietary": ["vegetarian"], "budget": 2, "home_city": "san diego"}
        updated = apply_changes(current, ProfileChanges(liked_cuisines=["thai"]))
        assert updated["dietary"] == ["vegetarian"]
        assert updated["budget"] == 2
        assert updated["home_city"] == "san diego"
        assert updated["liked_cuisines"] == ["thai"]

    def test_scalars_overwrite(self):
        updated = apply_changes({**_EMPTY, "budget": 2}, ProfileChanges(budget=4, home_city="Austin, TX"))
        assert updated["budget"] == 4
        assert updated["home_city"] == "austin"
        assert updated["home_city_display"] == "Austin, TX"

    def test_newly_liked_cuisine_leaves_the_disliked_list(self):
        current = {**_EMPTY, "disliked_cuisines": ["sushi", "indian"]}
        updated = apply_changes(current, ProfileChanges(liked_cuisines=["sushi"]))
        assert updated["liked_cuisines"] == ["sushi"]
        assert updated["disliked_cuisines"] == ["indian"]

    def test_newly_disliked_cuisine_leaves_the_liked_list(self):
        current = {**_EMPTY, "liked_cuisines": ["sushi", "thai"]}
        updated = apply_changes(current, ProfileChanges(disliked_cuisines=["sushi"]))
        assert updated["liked_cuisines"] == ["thai"]
        assert updated["disliked_cuisines"] == ["sushi"]


class TestInputCleaning:
    def test_profile_input_is_normalized(self):
        changes = build_profile_changes(
            platform=" Muse ",
            home_city="  San Diego ",
            dietary=["Veggie"],
            liked_cuisines=["Thai food", "Burger"],
            notes="hates long waits, reach me at sam@example.com",
        )
        assert changes.platform == "muse"
        assert changes.home_city == "San Diego"
        assert changes.dietary == ["vegetarian"]
        assert changes.liked_cuisines == ["thai", "burgers"]
        assert changes.notes == "hates long waits, reach me at"

    def test_remove_matches_every_normal_form(self):
        changes = build_profile_changes(remove=["Veggie", "Burger"])
        assert "vegetarian" in changes.remove
        assert "burgers" in changes.remove

    def test_removing_a_diet_end_to_end(self):
        current = {**_EMPTY, "dietary": ["vegetarian", "halal"]}
        updated = apply_changes(current, build_profile_changes(remove=["veggie"]))
        assert updated["dietary"] == ["halal"]

    def test_feedback_details_are_cleaned(self):
        details = build_feedback_details(
            comment="Amazing broth. Tell @sam!",
            visit_context="date",
            dishes=[
                DishOpinion("Spicy Miso Ramen", "positive"),
                DishOpinion("rice", "meh"),
                DishOpinion("   ", "positive"),
            ],
            vibe_tags=["Cozy", "cozy"],
            dietary_tags=["GF"],
        )
        assert details.comment == "Amazing broth. Tell !"
        assert details.occasion == "date night"
        assert [dish.name for dish in details.dishes] == ["Spicy Miso Ramen"]
        assert details.vibe_tags == ["cozy"]
        assert details.dietary_tags == ["gluten-free"]
