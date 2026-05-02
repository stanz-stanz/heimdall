"""X-Request-ID middleware — Stage A.5 spec §4.3.

Generates / validates / propagates a per-request correlation id so a
single operator action reads as one ``console.audit_log`` row + one
``clients.audit_log`` (or ``config_changes``) row + N log lines, all
stitched by one ``request_id``.

Mount order (locked by spec §4.3.3): :class:`RequestIdMiddleware`
mounts LAST in ``create_app`` so it sits OUTERMOST and every
downstream layer (``RequestLoggingMiddleware``, ``SessionAuthMiddleware``,
the route handler, the WebSocket adapter) reads
``request.state.request_id`` already populated.

Wire contract (§4.3.1):
- inbound ``X-Request-ID`` matches ``^[A-Za-z0-9_-]{1,128}$`` → use verbatim
- present but malformed (length / charset) → ignore, fresh UUIDv4
- absent → generate UUIDv4
- outbound: every HTTP response carries ``X-Request-ID: <value>``

The format guard prevents header-splitting (``\\r\\n`` injection) and
4096-character strings polluting the audit log. The 128-char cap
matches sensible distributed-tracing IDs (W3C ``traceparent`` is
55 chars). The character class ``[A-Za-z0-9_-]`` covers UUID, ULID,
hex, base64url-without-padding.

WebSocket scope is populated identically (state["request_id"] set on
the ASGI scope). The header echo is HTTP-only — the WS upgrade has
no response-header surface for downstream middleware to inject into,
so the WS adapter at ``src/api/console.py:_WSRequestAdapter`` reads
``state["request_id"]`` from the scope directly.
"""

from __future__ import annotations

import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Header name in the canonical lowercase form ASGI uses on the wire.
REQUEST_ID_HEADER = "x-request-id"

# Format guard. 128-char ceiling; URL-safe base64-style alphabet.
# Anchored so partial matches (e.g. embedded newline) cannot pass.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_or_generate(value: str | None) -> str:
    """Return ``value`` if it satisfies the format guard, else a fresh UUIDv4.

    Treats ``None``, empty string, or any non-conforming input as
    "generate fresh." Caller does not need to pre-strip / normalise —
    the regex is the canonical gate.
    """
    if value and _REQUEST_ID_PATTERN.match(value):
        return value
    return str(uuid.uuid4())


class RequestIdMiddleware:
    """ASGI middleware that propagates ``X-Request-ID`` end-to-end.

    Sets ``scope['state']['request_id']`` so any downstream middleware
    or handler can read ``request.state.request_id``. For HTTP
    responses also injects the header into ``http.response.start``
    so the value echoes back to the client (and to any reverse-proxy
    log).

    For WebSocket upgrades the scope is populated but no header is
    injected — the WS handshake response is opaque to ASGI middleware.
    The downstream adapter reads ``websocket.scope.get("state", {}).
    get("request_id")`` directly.

    Non-HTTP / non-WS scopes (lifespan) pass through untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Headers in the ASGI scope are a list of (bytes, bytes) tuples.
        # Convert once to a dict keyed by lowercase bytes for cheap lookup.
        headers = dict(scope.get("headers") or [])
        raw = headers.get(REQUEST_ID_HEADER.encode("latin-1"))
        request_id = _validate_or_generate(
            raw.decode("latin-1", errors="replace") if raw else None
        )

        # ``scope['state']`` is the canonical backing dict for
        # ``Request.state`` in Starlette / FastAPI. SessionAuthMiddleware
        # follows the same pattern (see src/api/auth/middleware.py:252).
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        if scope["type"] == "websocket":
            # No response-header surface on WS upgrades; the adapter
            # reads scope state directly.
            await self.app(scope, receive, send)
            return

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.append(
                    (
                        REQUEST_ID_HEADER.encode("latin-1"),
                        request_id.encode("latin-1"),
                    )
                )
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
