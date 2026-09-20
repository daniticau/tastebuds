"""Per-client rate limit as plain ASGI middleware.

It covers every route, including the mounted MCP app. Behind a proxy (Railway) every
request arrives from the proxy's address, so the client key comes from the proxy
headers: X-Real-IP, then the last X-Forwarded-For hop. The proxy appends the last
hop itself. A client can fake the earlier hops, so the code ignores them.
"""

import time
from collections import deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_WINDOW_SECONDS = 60.0
_MAX_TRACKED_CLIENTS = 50_000
_EXEMPT_PATHS = {"/health"}


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, per_minute: int, trust_proxy_headers: bool) -> None:
        self.app = app
        self.per_minute = per_minute
        self.trust_proxy_headers = trust_proxy_headers
        self._hits: dict[str, deque[float]] = {}

    def _client_key(self, scope: Scope) -> str:
        if self.trust_proxy_headers:
            headers = {name: value.decode("latin-1") for name, value in scope.get("headers", [])}
            real_ip = headers.get(b"x-real-ip", "").strip()
            if real_ip:
                return real_ip
            last_hop = headers.get(b"x-forwarded-for", "").split(",")[-1].strip()
            if last_hop:
                return last_hop
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _allow(self, key: str) -> bool:
        now = time.monotonic()
        if len(self._hits) > _MAX_TRACKED_CLIENTS:
            self._hits.clear()

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > _WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self.per_minute:
            return False
        hits.append(now)
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        if self._allow(self._client_key(scope)):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Slow down and try again in a minute."},
            headers={"Retry-After": "60"},
        )
        await response(scope, receive, send)
