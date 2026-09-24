"""A blocked search waits out the rate limit; it does not rotate the browser.

Rotating was tried and does not work: the block URL carries the same visitor id
across fresh sessions with an empty cookie jar.
"""
import asyncio

import pytest

from meal_to_cart import cart
from meal_to_cart.cart import _search_with_retry
from meal_to_cart.walmart import WalmartBlocked

PRODUCT = [{"item_id": "1", "title": "Dill, fresh", "price": 1.99, "price_text": "$1.99"}]


class FlakyMatcher:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    async def search(self, query, limit=5):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise WalmartBlocked(query)
        return PRODUCT


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    """The real backoff is 45 seconds; the test only cares about the sequence."""
    monkeypatch.setattr(cart, "BLOCK_BACKOFF", 0.0)


def test_a_block_waits_then_succeeds():
    matcher = FlakyMatcher(fail_times=1)
    assert asyncio.run(_search_with_retry(matcher, "dill")) == PRODUCT
    assert matcher.calls == 2


def test_a_permanent_block_gives_up_rather_than_looping():
    matcher = FlakyMatcher(fail_times=99)
    with pytest.raises(WalmartBlocked):
        asyncio.run(_search_with_retry(matcher, "dill"))
    assert matcher.calls == cart.BLOCK_ATTEMPTS


def test_a_block_never_calls_restart_because_rotation_does_not_help():
    class Watched(FlakyMatcher):
        restarts = 0

        async def restart(self):
            Watched.restarts += 1

    asyncio.run(_search_with_retry(Watched(fail_times=1), "dill"))
    assert Watched.restarts == 0
