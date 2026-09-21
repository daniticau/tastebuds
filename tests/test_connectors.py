"""Connector compatibility: Muse, Instinct, Grok Bot, and Poke.

Each class below copies how one platform talks to an MCP server, as far as public
sources describe it. The tests run against the real server in a subprocess, over real HTTP.

- Muse writes a client with the official MCP SDK, calls every tool once to test it,
  and keeps what it learned as a skill.
- Instinct keeps one Mcp-Session-Id for all calls and can fall back to plain HTTP.
- Grok Bot takes a name, a URL, and optional headers. It probes for OAuth first.
- Poke sends X-Poke-User-Id on every request and reads the server instructions.

Nothing here needs a database: every write is a dry run or fails on purpose.
The one full conversation at the end runs only when a database is configured.
"""

import json
import os
from contextlib import asynccontextmanager
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from tastebuds.identity import mint_taste_id, sanitize_taste_id

_ALL_TOOLS = {
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
_READ_ONLY_TOOLS = {"search_recommendations", "get_trending", "get_taste_profile"}
_JSON = {"Content-Type": "application/json"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    """Run the app the way production does: its own process, real HTTP.

    Set TASTEBUDS_TEST_SERVER_URL to aim the same tests at a server that already runs,
    for example the production Docker image or a staging deploy.
    """
    external = os.environ.get("TASTEBUDS_TEST_SERVER_URL")
    if external:
        yield external.rstrip("/")
        return

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "TASTEBUDS_PUBLIC_BASE_URL": base_url}
    if not env.get("TASTEBUDS_DATABASE_URL"):
        # No database: the server runs degraded. One connect attempt keeps the tests fast.
        env["TASTEBUDS_DATABASE_URL"] = "postgresql://unused@127.0.0.1:1/none"
        env["TASTEBUDS_DB_CONNECT_ATTEMPTS"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tastebuds.main:app", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                if httpx.get(f"{base_url}/llms.txt", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail("The server did not start")
            time.sleep(0.2)
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=10)


@asynccontextmanager
async def _sdk_session(server: str, headers: dict[str, str] | None = None):
    """Connect the way Muse does: the official SDK client over streamable HTTP."""
    async with create_mcp_http_client(headers=headers) as http_client:
        async with streamable_http_client(f"{server}/mcp", http_client=http_client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                session.init_result = await session.initialize()
                yield session


def _structured(result) -> dict:
    return getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)


def _is_error(result) -> bool:
    name = "is_error" if hasattr(result, "is_error") else "isError"
    return bool(getattr(result, name))


def _rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


def _call(name: str, **arguments) -> dict:
    return _rpc("tools/call", {"name": name, "arguments": arguments})


def _tool_result(response: httpx.Response) -> dict:
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert not result.get("isError"), result
    return result["structuredContent"]


class TestMuse:
    """Official SDK client. Tests every tool on setup. Optional bearer key."""

    async def test_setup_as_muse_does_it(self, server):
        async with _sdk_session(server) as session:
            if True:
                init = session.init_result
                server_info = getattr(init, "server_info", None) or init.serverInfo
                assert server_info.name == "Tastebuds"
                assert "Tastebuds playbook" in init.instructions

                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == _ALL_TOOLS

                # Muse calls each tool once. Every call must come back clean and store nothing.
                token = mint_taste_id()
                test_calls = {
                    "start_taste_profile": {"dry_run": True, "favorite_places": ["Test Cafe"]},
                    "search_recommendations": {"city": "Testville"},
                    "log_feedback": {"place_name": "Test Cafe", "sentiment": "positive", "dry_run": True},
                    "get_trending": {"city": "Testville"},
                    "get_taste_profile": {"taste_id": token},
                    "update_taste_profile": {"taste_id": token, "dietary": ["vegan"], "dry_run": True},
                    "delete_taste_profile": {"taste_id": token},
                    "get_follow_ups": {"taste_id": token},
                    "create_circle": {"taste_id": token, "dry_run": True},
                    "join_circle": {"taste_id": token, "invite_code": "k7m2-9xqd"},
                    "leave_circle": {"taste_id": token, "invite_code": "k7m2-9xqd"},
                    "invite_friend": {"taste_id": token, "dry_run": True},
                    "accept_friend_invite": {"taste_id": token, "invite_code": "k7m2-9xqd-4wte"},
                    "update_friend": {"taste_id": token, "friend_ref": "k7m2-9xqd-4wte", "closeness": 2},
                }
                assert set(test_calls) == _ALL_TOOLS
                for name, arguments in test_calls.items():
                    result = await session.call_tool(name, arguments)
                    assert not _is_error(result), (name, result.content)
                    assert isinstance(_structured(result), dict), name
                    # Every answer tells the agent what happened, in words.
                    assert _structured(result).get("message") or _structured(result).get(
                        "success"
                    ), (name, _structured(result))

    async def test_the_playbook_survives_a_client_that_skips_instructions(self, server):
        async with _sdk_session(server) as session:
            if True:
                result = await session.call_tool("start_taste_profile", {"dry_run": True})
                content = _structured(result)
                assert "Tastebuds recommends" in content["playbook"]
                assert sanitize_taste_id(content["taste_id"]) == content["taste_id"]
                assert "taste_id" in content["remember"]

    async def test_a_stored_bearer_key_carries_the_identity(self, server):
        token = mint_taste_id()
        headers = {"Authorization": f"Bearer {token}"}
        async with _sdk_session(server, headers) as session:
            if True:
                result = await session.call_tool("start_taste_profile", {"dry_run": True})
                assert _structured(result)["taste_id"] == token

    async def test_old_clients_can_read_the_result_as_text(self, server):
        async with _sdk_session(server) as session:
            if True:
                result = await session.call_tool("invite_friend", {"taste_id": mint_taste_id(), "dry_run": True})
                assert json.loads(result.content[0].text) == _structured(result)


class TestToolSchemas:
    """What every platform's model sees. Simple schemas fail less."""

    @pytest.fixture()
    def tools(self, server):
        response = httpx.post(f"{server}/mcp", json=_rpc("tools/list"), headers=_JSON)
        return {tool["name"]: tool for tool in response.json()["result"]["tools"]}

    def test_every_tool_has_a_title_a_description_and_hints(self, tools):
        assert set(tools) == _ALL_TOOLS
        for name, tool in tools.items():
            assert tool.get("title"), name
            assert len(tool["description"]) > 40, name
            assert tool["annotations"]["openWorldHint"] is False, name

    def test_hints_separate_reads_writes_and_the_one_delete(self, tools):
        for name, tool in tools.items():
            hints = tool["annotations"]
            assert hints["readOnlyHint"] is (name in _READ_ONLY_TOOLS), name
            if name not in _READ_ONLY_TOOLS:
                # Only a real delete may ask the person to confirm. Logging must stay silent.
                assert hints["destructiveHint"] is (name == "delete_taste_profile"), name

    def test_schemas_avoid_constructs_that_weak_clients_mishandle(self, tools):
        for name, tool in tools.items():
            schema = tool["inputSchema"]
            text = json.dumps(schema)
            assert schema["type"] == "object", name
            assert "$ref" not in text and "$defs" not in text, name
            for field, spec in schema["properties"].items():
                assert spec.get("description") or spec.get("title"), (name, field)
                items = spec.get("items") or next(
                    (option.get("items") for option in spec.get("anyOf", []) if option.get("items")),
                    None,
                )
                if items:
                    assert "anyOf" not in items and "oneOf" not in items, (name, field)

    def test_every_tool_works_with_no_required_argument_beyond_the_obvious(self, tools):
        required = {name: set(tool["inputSchema"].get("required", [])) for name, tool in tools.items()}
        assert required["log_feedback"] == {"place_name", "sentiment"}
        assert required["join_circle"] == required["leave_circle"] == {"invite_code"}
        assert required["accept_friend_invite"] == {"invite_code"}
        assert required["update_friend"] == {"friend_ref"}
        for name in _ALL_TOOLS - {"log_feedback", "join_circle", "leave_circle", "accept_friend_invite", "update_friend"}:
            assert required[name] == set(), name


class TestInstinct:
    """A hand-written client on a cloud computer. It keeps one session id for every call."""

    def test_a_session_id_from_before_a_deploy_still_works(self, server):
        headers = {**_JSON, "Accept": "application/json", "Mcp-Session-Id": "kept-since-last-week"}
        with httpx.Client(base_url=server, headers=headers) as client:
            # No initialize: after our deploy the client does not know it should start over.
            result = _tool_result(client.post("/mcp", json=_call("start_taste_profile", dry_run=True)))
            assert sanitize_taste_id(result["taste_id"])
            again = _tool_result(client.post("/mcp/", json=_call("log_feedback", place_name="Tajima Ramen", sentiment="positive", dry_run=True)))
            assert again["dry_run"] is True

    @pytest.mark.parametrize("accept", ["application/json", "*/*", "text/event-stream", None])
    def test_any_accept_header_gets_plain_json(self, server, accept):
        headers = {**_JSON, **({"Accept": accept} if accept else {})}
        response = httpx.post(f"{server}/mcp", json=_rpc("tools/list"), headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert len(response.json()["result"]["tools"]) == len(_ALL_TOOLS)

    def test_forgiving_input_from_a_client_without_schema_validation(self, server):
        result = _tool_result(
            httpx.post(
                f"{server}/mcp",
                headers=_JSON,
                json=_call(
                    "log_feedback",
                    place_name="Tajima Ramen",
                    sentiment="positive",
                    dishes="spicy miso ramen",          # text, not a list of objects
                    cuisine_tags="ramen, japanese",     # text, not a list
                    price_level="2",                    # text, not a number
                    dry_run=True,
                ),
            ),
        )
        assert result["success"] is True

    def test_the_page_route_works_without_any_mcp_client(self, server):
        guide = httpx.get(f"{server}/llms.txt").text
        assert "/mcp" in guide and "/api/v1/" in guide and "start_taste_profile" in guide
        response = httpx.post(f"{server}/api/v1/start_taste_profile", json={"dry_run": True, "platform": "instinct"})
        assert sanitize_taste_id(response.json()["taste_id"])


class TestGrokBot:
    """A name, a URL, and optional headers. OAuth probes first. Hints decide confirmations."""

    @pytest.mark.parametrize(
        "path",
        [
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        ],
    )
    def test_oauth_probes_learn_that_no_sign_in_is_needed(self, server, path):
        response = httpx.get(f"{server}{path}")
        assert response.status_code == 404

    def test_no_request_is_ever_challenged_for_credentials(self, server):
        response = httpx.post(f"{server}/mcp", json=_rpc("tools/list"), headers=_JSON)
        assert response.status_code == 200
        assert "www-authenticate" not in response.headers

    def test_an_unrelated_key_in_the_optional_headers_is_ignored(self, server):
        headers = {**_JSON, "Authorization": "Bearer some-key-the-person-pasted", "X-Api-Key": "whatever"}
        result = _tool_result(httpx.post(f"{server}/mcp", headers=headers, json=_call("start_taste_profile", dry_run=True)))
        assert result["taste_id"].startswith("tb_")

    @pytest.mark.parametrize("version", ["2024-11-05", "2025-06-18", "2025-11-25", "2027-01-01"])
    def test_old_and_future_protocol_versions_both_connect(self, server, version):
        params = {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "grok-bot", "version": "1"}}
        response = httpx.post(f"{server}/mcp", json=_rpc("initialize", params), headers=_JSON)
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["serverInfo"]["name"] == "Tastebuds"
        assert result["protocolVersion"]  # the server offers a version it supports

    def test_browser_based_setup_from_another_origin_is_not_blocked(self, server):
        headers = {**_JSON, "Origin": "https://grok.com"}
        assert httpx.post(f"{server}/mcp", json=_rpc("tools/list"), headers=headers).status_code == 200


class TestPoke:
    """Streamable HTTP first. X-Poke-User-Id on every request. Reads the server instructions."""

    _USER = str(uuid.uuid4())

    def test_instructions_carry_the_playbook(self, server):
        params = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "poke", "version": "1"}}
        headers = {**_JSON, "X-Poke-User-Id": self._USER}
        result = httpx.post(f"{server}/mcp", json=_rpc("initialize", params), headers=headers).json()["result"]
        assert "Tastebuds recommends" in result["instructions"]
        assert "start_taste_profile" in result["instructions"]

    def test_the_poke_user_id_never_comes_back(self, server):
        headers = {**_JSON, "X-Poke-User-Id": self._USER}
        for body in (
            _call("start_taste_profile", dry_run=True, platform="poke"),
            _call("get_taste_profile", taste_id=mint_taste_id()),
            _rpc("tools/list"),
        ):
            response = httpx.post(f"{server}/mcp", json=body, headers=headers)
            assert response.status_code == 200
            assert self._USER not in response.text

    def test_the_old_recipe_still_works(self, server):
        """The first Poke recipe sent a UUID it made up as taste_id, and always sent a city."""
        legacy_token = str(uuid.uuid4())
        headers = {**_JSON, "X-Poke-User-Id": self._USER}
        result = _tool_result(
            httpx.post(
                f"{server}/mcp",
                headers=headers,
                json=_call(
                    "log_feedback",
                    place_name="Sab E Lee",
                    city="San Diego",
                    sentiment="positive",
                    visit_context="dinner",
                    taste_id=legacy_token,
                    dry_run=True,
                ),
            ),
        )
        assert result["success"] is True


@pytest.mark.integration
class TestFullConversation:
    """One real conversation over the SDK client, from first text to a friend's pick."""

    async def test_onboard_recommend_learn_and_share(self, server):
        city = f"Connector City {uuid.uuid4().hex[:8]}"
        async with _sdk_session(server) as session:
            if True:

                async def call(name, **arguments):
                    result = await session.call_tool(name, arguments)
                    assert not _is_error(result), (name, result.content)
                    return _structured(result)

                me = (await call("start_taste_profile", platform="muse", home_city=city, dietary="vegetarian"))["taste_id"]
                friends = []
                for place in ("Nonna Pia Trattoria", "Blue Harbor Sushi"):
                    friend = await call("start_taste_profile", platform="grokbot", home_city=city, favorite_places=place)
                    friends.append(friend["taste_id"])
                    invite = await call("invite_friend", taste_id=me, closeness=3)
                    await call("accept_friend_invite", taste_id=friend["taste_id"], invite_code=invite["friend_ref"])

                picks = await call("search_recommendations", taste_id=me)
                assert {place["name"] for place in picks["recommendations"]} == {"Nonna Pia Trattoria", "Blue Harbor Sushi"}
                assert "Tastebuds recommends" in picks["agent_note"]
                assert "someone close to them liked it" in picks["recommendations"][0]["why"]

                logged = await call(
                    "log_feedback",
                    taste_id=me,
                    place_name="nonna pia",
                    sentiment="positive",
                    dishes=[{"name": "cacio e pepe", "sentiment": "positive"}],
                    occasion="date",
                )
                assert logged["place_name"] == "Nonna Pia Trattoria"

                profile = (await call("get_taste_profile", taste_id=me))["profile"]
                assert profile["dietary"] == ["vegetarian"]
                assert profile["learned"]["loved_places"] == ["Nonna Pia Trattoria"]
                assert profile["friend_signals_active"] is True

                for token in (me, *friends):
                    await call("delete_taste_profile", taste_id=token, confirm=True)
