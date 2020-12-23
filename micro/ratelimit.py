# ratelimit
# Released into the public domain
# https://github.com/noyainrain/micro/blob/master/micro/ratelimit.py

"""Mechanism to limit the rate of operations per client."""

from asyncio import get_event_loop
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Tuple

@dataclass(frozen=True)
class RateLimit:
    """Rate limit rule for an operation.

    .. attribute:: id

       Unique ID of the rule.

    .. attribute:: n

       Maximum number of operations.

    .. attribute:: time_frame

       Reference time frame.
    """
    id: str
    n: int
    time_frame: timedelta

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError('Empty id')
        if self.n <= 0:
            raise ValueError('Out-of-range n')
        if self.time_frame <= timedelta():
            raise ValueError('Out-of-range time_frame')

class RateLimiter:
    """Mechanism to limit the rate of operations per client."""

    def __init__(self) -> None:
        self._counters: Dict[Tuple[RateLimit, str], int] = {}

    def count(self, limit: RateLimit, client: str) -> None:
        """Count an operation by *client*.

        The operation is defined by *limit*. *client* is an identifier, e.g. a network address. If
        the client exceeds the allowed rate limit, a :exc:`RateLimitError` is raised.
        """
        key = (limit, client)
        if key not in self._counters:
            self._counters[key] = 0
            get_event_loop().call_later(limit.time_frame.total_seconds(),
                                        lambda: self._counters.pop(key))
        self._counters[key] += 1
        if self._counters[key] > limit.n:
            raise RateLimitError(client)

class RateLimitError(Exception):
    """Raised if a client exceeds the allowed rate limit for an operation."""
