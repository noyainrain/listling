# ratelimit
# Released into the public domain
# https://github.com/noyainrain/micro/blob/master/micro/ratelimit.py

# pylint: disable=missing-docstring; test module

from asyncio import sleep
from datetime import timedelta
from tornado.testing import AsyncTestCase, gen_test

from micro.ratelimit import RateLimit, RateLimiter, RateLimitError

class RateLimiterTest(AsyncTestCase):
    LIMIT = RateLimit('meow', 2, timedelta(seconds=0.1))

    def setUp(self) -> None:
        super().setUp()
        self.rate_limiter = RateLimiter()

    def test_count(self) -> None:
        self.rate_limiter.count(self.LIMIT, 'local')
        self.rate_limiter.count(self.LIMIT, 'local')
        with self.assertRaises(RateLimitError):
            self.rate_limiter.count(self.LIMIT, 'local')

    @gen_test # type: ignore
    async def test_count_after_time_frame(self) -> None:
        self.rate_limiter.count(self.LIMIT, 'local')
        self.rate_limiter.count(self.LIMIT, 'local')
        await sleep(0.2)
        self.rate_limiter.count(self.LIMIT, 'local')
