from tastebuds.taxonomy import (
    cuisine_search_terms,
    cuisine_tags_for_place,
    normalize_cuisine,
    normalize_cuisines,
    normalize_dietary,
    normalize_occasion,
    normalize_tags,
)


class TestCuisine:
    def test_strips_noise_words(self):
        assert normalize_cuisine("Mexican food") == "mexican"
        assert normalize_cuisine("Thai Restaurant") == "thai"

    def test_synonyms(self):
        assert normalize_cuisine("Burger") == "burgers"
        assert normalize_cuisine("barbecue") == "bbq"
        assert normalize_cuisine("Bubble Tea") == "boba"
        assert normalize_cuisine("coffee shop") == "coffee"

    def test_keeps_accents(self):
        assert normalize_cuisine("banh mi") == "bánh mì"
        assert normalize_cuisine("bánh mì") == "bánh mì"

    def test_list_dedupes_in_order(self):
        assert normalize_cuisines(["Thai", "thai food", "Burger", ""]) == ["thai", "burgers"]

    def test_place_tags_gain_parents(self):
        assert cuisine_tags_for_place(["ramen"]) == ["ramen", "japanese", "noodles"]
        assert cuisine_tags_for_place(["taco", "mexican"]) == ["tacos", "mexican"]

    def test_broad_search_finds_children(self):
        terms = cuisine_search_terms("Japanese food")
        assert terms[0] == "japanese"
        assert {"ramen", "sushi", "izakaya"} <= set(terms)

    def test_narrow_search_stays_narrow(self):
        assert cuisine_search_terms("ramen") == ["ramen"]

    def test_empty_search(self):
        assert cuisine_search_terms("  ") == []


class TestOtherVocabulary:
    def test_dietary_synonyms(self):
        assert normalize_dietary(["Veggie", "GF", "plant-based", "halal"]) == [
            "vegetarian",
            "gluten-free",
            "vegan",
            "halal",
        ]

    def test_dietary_dedupes(self):
        assert normalize_dietary(["vegetarian", "veggie", "Vegetarian-Friendly"]) == ["vegetarian"]

    def test_occasion(self):
        assert normalize_occasion("Date") == "date night"
        assert normalize_occasion("with kids") == "family"
        assert normalize_occasion("brunch") == "brunch"
        assert normalize_occasion(None) is None
        assert normalize_occasion("   ") is None

    def test_tags_are_cleaned_and_capped(self):
        assert normalize_tags(["  Cozy ", "LOUD!!", "cozy", ""]) == ["cozy", "loud"]
        assert len(normalize_tags(["x" * 100])[0]) == 40


class TestInferFromName:
    def test_reads_cuisine_out_of_the_name(self):
        from tastebuds.taxonomy import infer_cuisines_from_name

        assert infer_cuisines_from_name("Tajima Ramen") == ["ramen"]
        assert infer_cuisines_from_name("Joe's Pizza") == ["pizza"]
        assert infer_cuisines_from_name("Smoky Oak Barbecue") == ["bbq"]
        assert infer_cuisines_from_name("Golden Lotus Thai Kitchen") == ["thai"]
        assert infer_cuisines_from_name("Seoul Korean BBQ") == ["korean", "bbq", "korean bbq"]
        assert infer_cuisines_from_name("Lucha Libre Taco Shop") == ["tacos"]

    def test_names_without_a_hint_give_nothing(self):
        from tastebuds.taxonomy import infer_cuisines_from_name

        for name in ("Hodad's", "Juniper & Ivy", "The Dinner Bell", "Morning Glory"):
            assert infer_cuisines_from_name(name) == [], name
