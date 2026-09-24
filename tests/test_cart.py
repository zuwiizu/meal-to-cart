import asyncio

from meal_to_cart.cart import apply
from meal_to_cart.models import Buy, MatchResult


class FakeGateway:
    def __init__(self):
        self.added = []

    async def add(self, item_id, quantity=1):
        self.added.append((item_id, quantity))
        return "ok"

    async def view_cart(self):
        return "cart"


def _add(**kw):
    base = {"buy": Buy(item="feta"), "query": "feta", "item_id": "1",
            "action": "add", "confidence": 0.9}
    base.update(kw)
    return MatchResult(**base)


def test_flagged_items_are_never_added():
    results = [_add(), MatchResult(buy=Buy(item="truffle honey"),
                                   query="truffle honey", action="flag")]
    gateway = FakeGateway()
    summary = asyncio.run(apply(results, gateway, approve=lambda r: True))
    assert gateway.added == [("1", 1)]
    assert summary["skipped_flagged"] == 1


def test_denied_items_are_not_added():
    gateway = FakeGateway()
    summary = asyncio.run(apply([_add()], gateway, approve=lambda r: False))
    assert gateway.added == []
    assert summary["denied"] == 1


def test_an_item_with_no_id_is_never_added_even_if_approved():
    gateway = FakeGateway()
    summary = asyncio.run(apply([_add(item_id=None)], gateway, approve=lambda r: True))
    assert gateway.added == []
    assert summary["skipped_flagged"] == 1


def test_dry_run_never_touches_the_gateway():
    class Exploding(FakeGateway):
        async def add(self, *a, **k):
            raise AssertionError("a dry run must not write to the cart")

    summary = asyncio.run(apply([_add()], Exploding(), approve=lambda r: True,
                                dry_run=True))
    assert summary["would_add"] == 1
    assert summary["added"] == 0
