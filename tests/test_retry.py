"""A blocked search must rotate the session, not just wait longer."""
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
        self.restarts = 0

    async def search(self, query, limit=5):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise WalmartBlocked(query)
        return PRODUCT

    async def restart(self):
        self.restarts += 1


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    """The real backoff is seconds long; the test only cares about the order."""
    monkeypatch.setattr(cart, "BLOCK_BACKOFF", 0.0)


def test_a_block_rotates_the_session_then_succeeds():
    matcher = FlakyMatcher(fail_times=1)
    assert asyncio.run(_search_with_retry(matcher, "dill")) == PRODUCT
    assert matcher.calls == 2
    assert matcher.restarts == 1


def test_two_blocks_rotate_twice():
    matcher = FlakyMatcher(fail_times=2)
    assert asyncio.run(_search_with_retry(matcher, "dill")) == PRODUCT
    assert matcher.restarts == 2


def test_a_permanent_block_gives_up_rather_than_looping():
    matcher = FlakyMatcher(fail_times=99)
    with pytest.raises(WalmartBlocked):
        asyncio.run(_search_with_retry(matcher, "dill"))
    assert matcher.calls == cart.BLOCK_ATTEMPTS
