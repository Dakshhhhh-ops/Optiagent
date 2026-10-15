"""Abuse and cost protection: rate limits, request size limits and secure headers.

Limits are kept in memory, which is right for a single API instance (the free-tier setup).
Behind a load balancer with several instances they would need a shared store such as Redis.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from optiagent_api.settings import Settings, get_settings


class SlidingWindowLimiter:
    """Allow at most `limit` events per `window` seconds for each key."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> float | None:
        """Record an event. Returns None if allowed, else seconds until the next slot frees up."""
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                return max(events[0] + window - now, 0.0)
            events.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The caller's IP. Behind a proxy (Render, Fly) it is the first X-Forwarded-For entry."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def identity(request: Request, settings: Settings) -> str:
    """Rate-limit key: the signed-in user if known, otherwise the IP address."""
    user = getattr(request.state, "user_id", None)
    return f"user:{user}" if user else f"ip:{client_ip(request, settings.trust_proxy)}"


def _too_many(retry_after: float, what: str) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Too many {what}. Try again in {int(retry_after) + 1} seconds.",
        headers={"Retry-After": str(int(retry_after) + 1)},
    )


def limit_llm_calls(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Dependency for endpoints that call the LLM: per-caller and global daily limits."""
    wait = limiter.hit(f"llm:{identity(request, settings)}", settings.llm_requests_per_hour, 3600)
    if wait is not None:
        raise _too_many(wait, "AI requests")
    wait = limiter.hit("llm:global-day", settings.llm_requests_per_day, 86_400)
    if wait is not None:
        # Protects the provider bill if the site is hammered by many callers at once.
        raise HTTPException(
            503, "The AI service has reached its daily limit. Please try again tomorrow."
        )


class SecurityMiddleware(BaseHTTPMiddleware):
    """Per-IP request rate limit, request size limit and secure response headers."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()

        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_bytes:
            return JSONResponse(
                {"detail": f"Request larger than {settings.max_request_bytes // 1_000_000} MB."},
                status_code=413,
            )

        if request.url.path not in ("/health",):
            ip = client_ip(request, settings.trust_proxy)
            wait = limiter.hit(f"req:{ip}", settings.requests_per_minute, 60)
            if wait is not None:
                return JSONResponse(
                    {"detail": "Too many requests. Slow down a little."},
                    status_code=429,
                    headers={"Retry-After": str(int(wait) + 1)},
                )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
