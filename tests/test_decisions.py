"""Tests for the Jev layer. A fake HTTP transport stands in for api.typesafe.ai."""

import json

import httpx
import pytest

from tastebuds import decisions
from tastebuds.config import Settings
from tastebuds.decisions import KnownPlace

_CANDIDATES = [KnownPlace("Tajima", "Kearny Mesa", ["ramen"]), KnownPlace("Tajimi Sushi")]


def _configure(monkeypatch, handler, **overrides) -> list[httpx.Request]:
    """Turn Jev on with a fake key and route its HTTP calls to handler."""
    seen: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    settings = Settings(database_url="postgresql://unused", typesafe_api_key="sk-test", **overrides)
    monkeypatch.setattr(decisions, "get_settings", lambda: settings)
    monkeypatch.setattr(
        decisions,
        "_client",
        httpx.AsyncClient(transport=httpx.MockTransport(recording_handler)),
    )
    return seen


def _answers(**answers) -> httpx.Response:
    return httpx.Response(200, json={"model": "jev-1.13.0", "answers": answers})


async def _decide(need_cuisine=False, candidates=_CANDIDATES):
    return await decisions.decide_place(
        name="Tajima Ramen House",
        city="San Diego",
        neighborhood="Convoy",
        hints=["tonkotsu ramen"],
        candidates=candidates,
        need_cuisine=need_cuisine,
    )


class TestTransport:
    async def test_without_a_key_nothing_is_sent(self, monkeypatch):
        settings = Settings(database_url="postgresql://unused")
        monkeypatch.setattr(decisions, "get_settings", lambda: settings)
        monkeypatch.setattr(decisions, "_get_client", lambda: pytest.fail("no HTTP call expected"))
        assert await decisions.ask({"a": 1}, {"q": {"type": "noul", "instructions": "x"}}) is None
        assert await _decide() is None

    async def test_request_follows_the_documented_wire_format(self, monkeypatch):
        seen = _configure(monkeypatch, lambda request: _answers(same_as_0={"type": "noul", "noul": 0.9}))
        await _decide(candidates=_CANDIDATES[:1])

        request = seen[0]
        body = json.loads(request.content)
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["authorization"] == "Bearer sk-test"
        assert body["model"] == "jev-latest"
        assert body["state"]["new_mention"] == {
            "name": "Tajima Ramen House",
            "neighborhood": "Convoy",
            "dishes_mentioned": ["tonkotsu ramen"],
        }
        assert body["state"]["known_places"][0]["name"] == "Tajima"
        question = body["questions"]["same_as_0"]
        assert question["type"] == "noul"
        assert set(question["criteria"]) == {"true", "false"}

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(529, json={"error": "overloaded"}),
            httpx.Response(429),
            httpx.Response(401),
            httpx.Response(200, content=b"not json"),
            httpx.Response(200, json={"no_answers_key": True}),
            httpx.Response(200, json={"answers": ["wrong", "shape"]}),
        ],
    )
    async def test_any_failure_means_no_answer(self, monkeypatch, response):
        _configure(monkeypatch, lambda request: response)
        assert await _decide() is None

    async def test_a_slow_answer_means_no_answer(self, monkeypatch):
        def too_slow(request):
            raise httpx.ReadTimeout("slow", request=request)

        _configure(monkeypatch, too_slow)
        assert await _decide() is None


class TestPlaceDecision:
    async def test_picks_the_most_likely_known_place(self, monkeypatch):
        _configure(
            monkeypatch,
            lambda request: _answers(same_as_0={"noul": 0.93}, same_as_1={"noul": 0.04}),
        )
        decision = await _decide()
        assert decision.answered_sameness is True
        assert decision.same_as == 0

    async def test_no_match_is_also_an_answer(self, monkeypatch):
        _configure(
            monkeypatch,
            lambda request: _answers(same_as_0={"noul": 0.31}, same_as_1={"noul": 0.02}),
        )
        decision = await _decide()
        assert decision.answered_sameness is True
        assert decision.same_as is None

    async def test_a_partial_answer_falls_back_to_the_fixed_rule(self, monkeypatch):
        _configure(monkeypatch, lambda request: _answers(same_as_0={"noul": 0.93}))
        decision = await _decide()
        assert decision.answered_sameness is False
        assert decision.same_as is None

    async def test_the_threshold_is_configurable(self, monkeypatch):
        _configure(
            monkeypatch,
            lambda request: _answers(same_as_0={"noul": 0.75}, same_as_1={"noul": 0.1}),
            jev_same_place_threshold=0.9,
        )
        assert (await _decide()).same_as is None

    async def test_cuisine_is_asked_only_when_needed(self, monkeypatch):
        seen = _configure(monkeypatch, lambda request: _answers())
        await _decide(need_cuisine=False)
        assert "cuisine" not in json.loads(seen[0].content)["questions"]

    async def test_a_confident_cuisine_is_accepted(self, monkeypatch):
        seen = _configure(
            monkeypatch,
            lambda request: _answers(cuisine={"choice": "ramen", "confidence": 0.82}),
        )
        decision = await _decide(need_cuisine=True, candidates=[])
        assert decision.cuisine == "ramen"
        assert decision.answered_sameness is False

        options = json.loads(seen[0].content)["questions"]["cuisine"]["criteria"]
        assert "unknown" in options and "ramen" in options
        assert len(options) <= 255

    @pytest.mark.parametrize(
        "answer",
        [
            {"choice": "unknown", "confidence": 0.95},
            {"choice": "ramen", "confidence": 0.2},
            {"choice": "martian", "confidence": 0.99},
            {"choice": "ramen"},
        ],
    )
    async def test_a_weak_or_odd_cuisine_is_ignored(self, monkeypatch, answer):
        _configure(monkeypatch, lambda request: _answers(cuisine=answer))
        assert (await _decide(need_cuisine=True, candidates=[])).cuisine is None

    async def test_nothing_to_ask_sends_nothing(self, monkeypatch):
        seen = _configure(monkeypatch, lambda request: _answers())
        assert await _decide(need_cuisine=False, candidates=[]) is None
        assert seen == []


class TestCommentCheck:
    async def test_off_by_default_even_with_a_key(self, monkeypatch):
        seen = _configure(monkeypatch, lambda request: _answers(identifies_someone={"noul": 0.99}))
        assert await decisions.comment_identifies_someone("Went with Sarah from Acme.") is None
        assert seen == []

    async def test_returns_the_probability_when_on(self, monkeypatch):
        seen = _configure(
            monkeypatch,
            lambda request: _answers(identifies_someone={"noul": 0.88}),
            jev_check_comments=True,
        )
        assert await decisions.comment_identifies_someone("Went with Sarah from Acme.") == 0.88
        assert json.loads(seen[0].content)["state"] == "Went with Sarah from Acme."
