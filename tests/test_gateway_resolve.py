"""The seam and the gateway: a planned line becomes a product or a named
refusal, and a cart link is only ever built from Resolved lines.

The seam's two promises are the ones worth pinning: it refuses an unsized
line BEFORE any lookup runs, and it never searches on its own. Both are the
difference between a named hole and a cart that quietly looks complete.
"""
from __future__ import annotations

import pytest

from meal_to_cart import gateway
from meal_to_cart.mealplan.shopping import Buy
from meal_to_cart.resolve import NoProduct, Product, Resolved, Unknown, resolve


def _line(item="olive oil", buy="2 teaspoon"):
    return Buy(item=item, buy=buy)


class TestResolve:
    def test_a_sized_line_becomes_the_product_the_lookup_gave(self):
        line = _line()
        product = Product(item_id="1001", quantity=1, title="Olive Oil",
                          price=3.98, why="matched")
        answer = resolve(line, lookup=lambda l, r, w: product)
        assert isinstance(answer, Resolved)
        assert answer.line is line
        assert answer.item_id == "1001"
        assert answer.quantity == 1
        assert answer.cart_line() == ("1001", 1)

    def test_an_unsized_line_is_refused_before_any_lookup(self):
        calls = []

        def lookup(line, retailer, wanted):
            calls.append(line.item)
            return Product(item_id="1", quantity=1)

        answer = resolve(_line(item="olive oil", buy="as needed"),
                         lookup=lookup)
        assert isinstance(answer, Unknown)
        assert calls == [], "the seam must not ask about a line it already refuses"
        assert "olive oil" in answer.item
        assert "does not state one usable amount" in answer.reason

    def test_the_seam_never_searches_on_its_own(self):
        with pytest.raises(RuntimeError):
            resolve(_line())

    def test_the_lookups_refusal_is_carried_through_named(self):
        answer = resolve(
            _line(),
            lookup=lambda l, r, w: NoProduct("no product at the store matched this line"))
        assert isinstance(answer, Unknown)
        assert answer.reason == "no product at the store matched this line"

    def test_empty_amounts_are_an_absence_not_a_zero(self):
        for amount in ("", "to taste", "as needed", "some"):
            answer = resolve(_line(item="salt", buy=amount),
                             lookup=lambda l, r, w: Product(item_id="1", quantity=1))
            assert isinstance(answer, Unknown), amount


class TestGateway:
    def test_the_link_carries_every_line_and_the_store(self):
        rendered = gateway.render_cart_link(
            [("1001", 1), ("1002", 2)], "0000")
        url, blank, summary = rendered.partition("\n\n")
        assert blank == "\n\n"
        assert url.startswith(
            "https://www.walmart.com/sc/cart/addToCart?items=")
        assert url.endswith("&storeId=0000")
        assert "items=1001_1,1002_2&" in url
        assert summary, "the human half must exist"

    def test_an_empty_cart_is_refused(self):
        with pytest.raises(ValueError):
            gateway.render_cart_link([], "0000")

    def test_a_missing_store_is_refused(self):
        with pytest.raises(ValueError):
            gateway.render_cart_link([("1001", 1)], "")

    def test_the_base_url_carries_no_credential_words(self):
        for word in ("password", "session", "cookie", "token", "auth"):
            assert word not in gateway.BASE_URL.lower()
