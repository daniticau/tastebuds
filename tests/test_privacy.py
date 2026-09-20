from tastebuds.privacy import scrub_text


def test_keeps_a_normal_opinion():
    assert scrub_text("The broth was rich and the noodles were perfect.") == (
        "The broth was rich and the noodles were perfect."
    )


def test_removes_email():
    assert scrub_text("great spot, ask sam.lee@example.com about the patio") == (
        "great spot, ask about the patio"
    )


def test_removes_phone_numbers():
    assert scrub_text("call (619) 555-0134 to book") == "call to book"
    assert scrub_text("text +1 619-555-0134") == "text"


def test_removes_links_and_handles():
    assert scrub_text("saw it on https://example.com/post thanks @foodie_sam") == "saw it on thanks"


def test_keeps_prices_and_small_numbers():
    assert scrub_text("2 tacos for $5, open till 11") == "2 tacos for $5, open till 11"


def test_empty_results_become_none():
    assert scrub_text(None) is None
    assert scrub_text("   ") is None
    assert scrub_text("sam@example.com") is None


def test_caps_length():
    assert len(scrub_text("a" * 900, max_length=100)) == 100
