from tastebuds.identity import (
    mint_friend_invite_code,
    mint_invite_code,
    mint_taste_id,
    parse_bearer,
    request_bearer_token,
    resolve_taste_id,
    sanitize_friend_invite_code,
    sanitize_invite_code,
    sanitize_taste_id,
)

_LEGACY_UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0123456789ab"


class TestTasteId:
    def test_minted_token_is_valid(self):
        token = mint_taste_id()
        assert token.startswith("tb_")
        assert sanitize_taste_id(token) == token

    def test_minted_tokens_differ(self):
        assert len({mint_taste_id() for _ in range(200)}) == 200

    def test_token_has_no_lookalike_characters(self):
        body = "".join(mint_taste_id()[3:] for _ in range(50))
        assert not set(body) & set("ilou")

    def test_legacy_uuid_still_accepted(self):
        assert sanitize_taste_id(_LEGACY_UUID) == _LEGACY_UUID

    def test_case_and_whitespace_are_forgiven(self):
        token = mint_taste_id()
        assert sanitize_taste_id(f"  {token.upper()} ") == token

    def test_garbage_is_dropped(self):
        for value in (None, "", "user-123", "tb_short", "tb_" + "i" * 20, "'; DROP TABLE places;--"):
            assert sanitize_taste_id(value) is None


class TestResolve:
    def test_explicit_argument_wins(self):
        explicit, header = mint_taste_id(), mint_taste_id()
        reset = request_bearer_token.set(header)
        try:
            assert resolve_taste_id(explicit) == explicit
        finally:
            request_bearer_token.reset(reset)

    def test_falls_back_to_bearer_token(self):
        header = mint_taste_id()
        reset = request_bearer_token.set(header)
        try:
            assert resolve_taste_id(None) == header
            assert resolve_taste_id("not-a-token") == header
        finally:
            request_bearer_token.reset(reset)

    def test_no_identity(self):
        assert resolve_taste_id(None) is None

    def test_parse_bearer(self):
        token = mint_taste_id()
        assert parse_bearer(f"Bearer {token}") == token
        assert parse_bearer(f"bearer   {token}") == token
        assert parse_bearer("Basic abc") is None
        assert parse_bearer("Bearer nonsense") is None
        assert parse_bearer(None) is None


class TestInviteCode:
    def test_minted_code_round_trips(self):
        code = mint_invite_code()
        assert len(code) == 9 and code[4] == "-"
        assert sanitize_invite_code(code) == code

    def test_forgives_how_people_type(self):
        assert sanitize_invite_code("K7M2 9XQD") == "k7m2-9xqd"
        assert sanitize_invite_code("k7m29xqd") == "k7m2-9xqd"
        # People read zero as 'o' and one as 'l'.
        assert sanitize_invite_code("ko72-9lqd") == "k072-91qd"

    def test_rejects_malformed(self):
        for value in (None, "", "abc", "k7m2-9xqd-extra", "!!!!-!!!!"):
            assert sanitize_invite_code(value) is None


class TestFriendInviteCode:
    def test_minted_code_round_trips(self):
        code = mint_friend_invite_code()
        assert len(code) == 14 and code.count("-") == 2
        assert sanitize_friend_invite_code(code) == code
        assert sanitize_friend_invite_code(code.upper().replace("-", " ")) == code

    def test_friend_and_circle_codes_never_mix(self):
        assert sanitize_invite_code(mint_friend_invite_code()) is None
        assert sanitize_friend_invite_code(mint_invite_code()) is None
