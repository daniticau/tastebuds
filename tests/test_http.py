"""HTTP surface tests. No database needed: every tool call here is a dry run."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tastebuds import main
from tastebuds.db import profiles, queries
from tastebuds.identity import mint_taste_id, sanitize_taste_id
from tastebuds.main import create_app
from tastebuds.ratelimit import RateLimitMiddleware

_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
_MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test-agent", "version": "1.0"},
    },
}
_EXPECTED_TOOLS = {
    "start_taste_profile",
    "search_recommendations",
    "log_feedback",
    "get_trending",
    "get_taste_profile",
    "update_taste_profile",
    "delete_taste_profile",
    "get_follow_ups",
    "create_circle",
    "join_circle",
    "leave_circle",
    "invite_friend",
    "accept_friend_invite",
    "update_friend",
}


@pytest.fixture()
def client(monkeypatch):
    async def no_database():
        raise RuntimeError("no database in HTTP tests")

    monkeypatch.setattr(main, "init_db_pool", no_database)
    for module in (main, queries, profiles):
        monkeypatch.setattr(module, "get_pool", no_database)
    with TestClient(create_app()) as test_client:
        yield test_client


class TestPages:
    def test_landing_page_has_a_message_for_each_platform(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "__MESSAGES_JSON__" not in response.text
        for platform in ("muse", "instinct", "poke", "other"):
            assert f'"{platform}"' in response.text
        assert "/mcp" in response.text

    def test_llms_txt_tells_an_agent_how_to_connect(self, client):
        response = client.get("/llms.txt")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        for expected in ("/mcp", "/api/v1/", "/openapi.json", "start_taste_profile", "dry_run=true"):
            assert expected in response.text

    def test_openapi_lists_every_tool(self, client):
        document = client.get("/openapi.json").json()
        assert document["openapi"].startswith("3.1")
        assert {path.removeprefix("/api/v1/") for path in document["paths"]} == _EXPECTED_TOOLS

        log_feedback = document["paths"]["/api/v1/log_feedback"]["post"]
        schema = log_feedback["requestBody"]["content"]["application/json"]["schema"]
        assert set(schema["required"]) == {"place_name", "sentiment"}
        assert log_feedback["summary"].startswith("Record how a real meal went.")


class TestRestBridge:
    def test_onboarding_dry_run_returns_token_and_playbook(self, client):
        response = client.post(
            "/api/v1/start_taste_profile",
            json={"home_city": "San Diego", "favorite_places": ["Tajima Ramen"], "dry_run": True},
        )
        body = response.json()
        assert response.status_code == 200
        assert sanitize_taste_id(body["taste_id"]) == body["taste_id"]
        assert body["saved_favorites"] == []
        assert "Tastebuds playbook" in body["playbook"]
        assert "Tastebuds recommends" in body["playbook"]
        assert "taste_id" in body["remember"]

    def test_feedback_dry_run(self, client):
        response = client.post(
            "/api/v1/log_feedback",
            json={
                "place_name": "Tajima Ramen",
                "sentiment": "positive",
                "dishes": ["spicy miso ramen", {"name": "gyoza", "sentiment": "negative"}],
                "dry_run": True,
            },
        )
        assert response.json()["message"] == "Dry run. Nothing was stored."

    def test_generic_place_is_refused_with_a_clear_message(self, client):
        response = client.post(
            "/api/v1/log_feedback",
            json={"place_name": "that thai place", "sentiment": "positive", "dry_run": True},
        )
        assert response.json() == {
            "success": False,
            "message": "Place name is too generic to identify a specific restaurant.",
        }

    def test_bearer_token_identifies_the_person(self, client):
        token = mint_taste_id()
        response = client.post(
            "/api/v1/start_taste_profile",
            json={"dry_run": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.json()["taste_id"] == token

    def test_tools_that_need_identity_say_how_to_get_one(self, client):
        response = client.post("/api/v1/get_taste_profile", json={})
        body = response.json()
        assert body["success"] is False
        assert "start_taste_profile" in body["message"]

    def test_friend_invite_dry_run(self, client):
        response = client.post(
            "/api/v1/invite_friend",
            json={"taste_id": mint_taste_id(), "closeness": 3, "dry_run": True},
        )
        assert response.json()["dry_run"] is True

    def test_closeness_is_a_level_not_a_count(self, client):
        response = client.post(
            "/api/v1/invite_friend",
            json={"taste_id": mint_taste_id(), "closeness": 412},
        )
        assert response.status_code == 422

    def test_code_mixups_get_a_helpful_hint(self, client):
        token = mint_taste_id()
        friend_tool = client.post(
            "/api/v1/accept_friend_invite",
            json={"taste_id": token, "invite_code": "k7m2-9xqd"},
        )
        assert "join_circle" in friend_tool.json()["message"]
        circle_tool = client.post(
            "/api/v1/join_circle",
            json={"taste_id": token, "invite_code": "k7m2-9xqd-4wte"},
        )
        assert "accept_friend_invite" in circle_tool.json()["message"]

    def test_delete_needs_confirmation(self, client):
        response = client.post("/api/v1/delete_taste_profile", json={"taste_id": mint_taste_id()})
        assert response.json()["success"] is False
        assert "confirm=true" in response.json()["message"]

    def test_database_failure_is_not_leaked(self, client):
        response = client.post("/api/v1/search_recommendations", json={"city": "San Diego"})
        assert response.status_code == 200
        assert response.json()["message"] == "Something went wrong. Please try again."
        assert "no database" not in response.text

    def test_unknown_tool(self, client):
        assert client.post("/api/v1/drop_tables", json={}).status_code == 404

    def test_invalid_arguments(self, client):
        response = client.post(
            "/api/v1/log_feedback",
            json={"place_name": "Tajima Ramen", "sentiment": "amazing"},
        )
        assert response.status_code == 422
        assert response.json()["problems"][0]["field"] == "sentiment"

    def test_body_must_be_a_json_object(self, client):
        headers = {"Content-Type": "application/json"}
        assert client.post("/api/v1/log_feedback", content="not json", headers=headers).status_code == 400
        assert client.post("/api/v1/log_feedback", content="[1, 2]", headers=headers).status_code == 400

    def test_empty_body_means_no_arguments(self, client):
        response = client.post("/api/v1/start_taste_profile?x=1", content="")
        assert response.status_code == 200


class TestMcpEndpoint:
    @pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
    def test_both_paths_answer_without_a_redirect(self, client, path):
        response = client.post(path, json=_MCP_INITIALIZE, headers=_MCP_HEADERS, follow_redirects=False)
        assert response.status_code == 200
        assert "Tastebuds" in response.text
        # The playbook travels as the server instructions.
        assert "Tastebuds playbook" in response.text


class TestRateLimit:
    def _limited_app(self, per_minute: int, trust_proxy_headers: bool = True) -> TestClient:
        limited = FastAPI()

        @limited.get("/ping")
        async def ping():
            return {"ok": True}

        @limited.get("/health")
        async def health():
            return {"status": "ok"}

        limited.add_middleware(
            RateLimitMiddleware,
            per_minute=per_minute,
            trust_proxy_headers=trust_proxy_headers,
        )
        return TestClient(limited)

    def test_blocks_after_the_limit(self):
        client = self._limited_app(per_minute=3)
        statuses = [client.get("/ping").status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]

    def test_each_forwarded_client_has_its_own_budget(self):
        client = self._limited_app(per_minute=1)
        assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 429
        assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 200

    def test_a_faked_first_hop_does_not_reset_the_budget(self):
        client = self._limited_app(per_minute=1)
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.9"}).status_code == 429

    def test_real_ip_header_wins(self):
        client = self._limited_app(per_minute=1)
        headers = {"X-Real-IP": "203.0.113.5", "X-Forwarded-For": "9.9.9.9"}
        assert client.get("/ping", headers=headers).status_code == 200
        assert client.get("/ping", headers={**headers, "X-Forwarded-For": "8.8.8.8"}).status_code == 429

    def test_forwarded_header_is_ignored_when_untrusted(self):
        client = self._limited_app(per_minute=1, trust_proxy_headers=False)
        assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 429

    def test_health_check_is_never_limited(self):
        client = self._limited_app(per_minute=1)
        assert [client.get("/health").status_code for _ in range(5)] == [200] * 5
