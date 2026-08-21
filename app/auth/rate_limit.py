"""Small in-process authentication abuse limiter for the single-instance MVP."""

from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic


class AuthRateLimiter:
    def __init__(
        self,
        *,
        limit: int = 8,
        window_seconds: int = 900,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        attempts = self._attempts[key]
        while attempts and attempts[0] <= now - self._window:
            attempts.popleft()
        if len(attempts) >= self._limit:
            return False
        attempts.append(now)
        return True

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)
