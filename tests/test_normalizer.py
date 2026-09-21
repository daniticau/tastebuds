from tastebuds.normalizer import normalize_city, normalize_name


class TestNormalizeName:
    def test_basic_lowercase(self):
        assert normalize_name("Sab E Lee") == "sab e lee"

    def test_strip_possessive(self):
        assert normalize_name("Joe's Pizza") == "joe pizza"

    def test_strip_curly_possessive(self):
        assert normalize_name("Bob\u2019s Grill") == "bob"

    def test_remove_suffix_restaurant(self):
        assert normalize_name("Thai Kitchen Restaurant") == "thai kitchen"

    def test_remove_suffix_cafe(self):
        assert normalize_name("Morning Glory Cafe") == "morning glory"

    def test_remove_multiple_suffixes(self):
        assert normalize_name("Bob's Bar Grill") == "bob"

    def test_strip_address_on_ordinal(self):
        assert normalize_name("Sab E Lee on 5th") == "sab e lee"

    def test_strip_address_at_street(self):
        assert normalize_name("Pizza Place at Main St") == "pizza place"

    def test_collapse_whitespace(self):
        assert normalize_name("  Extra   Spaces  ") == "extra spaces"

    def test_remove_punctuation(self):
        assert normalize_name("Mama's Bakery & Cafe") == "mama bakery"

    def test_preserve_hyphens(self):
        assert normalize_name("Crack-Shack") == "crack-shack"

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_all_caps(self):
        assert normalize_name("TACOS EL GORDO") == "tacos el gordo"


class TestNormalizeCity:
    def test_basic(self):
        assert normalize_city("San Diego") == "san diego"

    def test_strip_state(self):
        assert normalize_city("San Diego, CA") == "san diego"

    def test_strip_full_state(self):
        assert normalize_city("San Diego, California") == "san diego"

    def test_whitespace(self):
        assert normalize_city("  Los Angeles  ") == "los angeles"

    def test_empty(self):
        assert normalize_city("") == ""


class TestGenericNames:
    def test_pointing_words_are_generic(self):
        from tastebuds.normalizer import is_generic_name

        for name in ("restaurant", "that thai place", "a cafe", "Sushi Bar", "the pizza place", "", "!!!"):
            assert is_generic_name(name), name

    def test_real_names_pass(self):
        from tastebuds.normalizer import is_generic_name

        for name in ("The Taco Stand", "Tajima Ramen", "Joe's Pizza", "Waffle House", "Din Tai Fung", "Crack Shack"):
            assert not is_generic_name(name), name


class TestCityAndDish:
    def test_city_nicknames(self):
        from tastebuds.normalizer import normalize_city

        assert normalize_city("SF") == "san francisco"
        assert normalize_city("NYC") == "new york"
        assert normalize_city("St. Louis, MO") == "saint louis"
        assert normalize_city("San Diego, CA") == "san diego"

    def test_dish_names_match_across_phrasing(self):
        from tastebuds.normalizer import normalize_dish

        assert normalize_dish("The Spicy Miso Ramen!") == normalize_dish("spicy miso ramen")
        assert normalize_dish("") == ""


class TestShortForms:
    def test_short_names_people_really_use(self):
        from tastebuds.normalizer import is_short_form

        assert is_short_form("nonna pia", "nonna pia trattoria")
        assert is_short_form("tajima ramen house", "tajima")
        assert is_short_form("din tai fung", "din tai fung utc")

    def test_generic_or_tiny_words_are_not_enough(self):
        from tastebuds.normalizer import is_short_form

        assert not is_short_form("thai", "golden lotus thai")
        assert not is_short_form("the taco", "the taco stand")
        assert not is_short_form("pho hoa", "pho hoa binh noodle")

    def test_different_names_are_not_short_forms(self):
        from tastebuds.normalizer import is_short_form

        assert not is_short_form("golden lotus", "golden dragon")
        assert not is_short_form("", "tajima")
