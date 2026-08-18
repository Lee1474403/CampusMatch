from collections import defaultdict, deque
from dataclasses import dataclass
import asyncio
import time

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class Limit:
    requests: int
    window_seconds: int


class InMemoryRateLimiter:
    """Small single-process limiter. Use Redis when the API runs in multiple processes."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: Limit) -> None:
        now = time.monotonic()
        cutoff = now - limit.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit.requests:
                retry_after = max(1, int(events[0] + limit.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后再试",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

    async def clear(self) -> None:
        async with self._lock:
            self._events.clear()


limiter = InMemoryRateLimiter()

LOGIN_LIMIT = Limit(5, 60)
REGISTER_LIMIT = Limit(10, 60 * 60)
RESEND_LIMIT = Limit(3, 60 * 60)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


async def limit_login(request: Request, identifier: str) -> None:
    ip = client_ip(request)
    normalized = identifier.strip().lower()
    await limiter.check(f"login:ip:{ip}", LOGIN_LIMIT)
    await limiter.check(f"login:identifier:{normalized}", LOGIN_LIMIT)


async def limit_register(request: Request) -> None:
    await limiter.check(f"register:ip:{client_ip(request)}", REGISTER_LIMIT)


async def limit_resend(request: Request, email: str) -> None:
    ip = client_ip(request)
    normalized = email.strip().lower()
    await limiter.check(f"resend:ip:{ip}", RESEND_LIMIT)
    await limiter.check(f"resend:email:{normalized}", RESEND_LIMIT)
