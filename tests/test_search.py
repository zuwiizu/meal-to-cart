"""The store's half: reading the page's own embedded data, scoring rows
deterministically, and stamping every answer onto the line it came from.
"""
from __future__ import annotations

import asyncio

import pytest

from meal_to_cart import cart
from meal_to_cart.match import THRESHOLD, score
from meal_to_cart.mealplan.shopping import Buy
from meal_to_cart.walmart import StorePageError, WalmartHTTP, products_from_next_data

BLOB = {"props": {"pageProps": {"initialData": {"searchResult": {"itemStacks": [
    {"items": [
        {"usItemId": "1000000001", "name": "Olive Oil Demo Brand, 1 Count",
         "priceInfo": {"currentPrice": {"price": 3.98, "priceString": "$3.98"}},
         "availabilityStatus": "IN_STOCK", "canAddToCart": True,
         "sellerName": "Walmart.com", "averageRating": "4.5"},
        {"usItemId": "1000000002", "name": "Fancy Oil Tin", "sponsored": True,
         "priceInfo": {"currentPrice": {"price": 12.0, "priceString": "$12.00"}},
         "availabilityStatus": "IN_STOCK", "canAddToCart": True,
         "sellerName": "Third Party"},
    ]},
]}}}}}


def _row(title, **overrides):
    row = {"title": title, "item_id": "1", "stock": "IN_STOCK",
           "out_of_stock": False, "can_add_to_cart": True,
           "seller": "Walmart.com", "sponsored": False,
           "promises_known": False, "price": 3.98, "price_text": "$3.98"}
    row.update(overrides)
    return row


class TestReadingTheBlob:
    def test_rows_come_out_in_one_shape(self):
        rows = products_from_next_data(BLOB)
        assert [row["item_id"] for row in rows] == ["1000000001", "1000000002"]
        first = rows[0]
        assert first["title"].startswith("Olive Oil")
        assert first["price"] == 3.98
        assert first["price_text"] == "$3.98"
        # Nothing was parsed about delivery, and the row says so.
        assert first["promises_known"] is False

    def test_the_limit_is_kept(self):
        assert len(products_from_next_data(BLOB, limit=1)) == 1

    def test_a_page_without_the_blob_is_an_error_not_a_guess(self):
        with pytest.raises(StorePageError):
            WalmartHTTP()._blob("<html><body>visible markup only</body></html>")

    def test_the_live_search_reads_an_embedded_blob(self):
        import json as _json
        html = ("<html><script id=\"__NEXT_DATA__\" "
                "type=\"application/json\">"
                + _json.dumps(BLOB) + "</script></html>")
        http = WalmartHTTP()
        http._fetch = lambda url: html          # the network stays out of it
        rows = asyncio.run(http.search("olive oil", limit=5))
        assert rows[0]["item_id"] == "1000000001"

    def test_a_tile_without_prices_is_none_not_zero(self):
        # Seen live 2026-09-30: the search blob came back with every tile's
        # priceInfo present but empty. An empty price must read as "no
        # price", never as $0.00, or a week's total would say "free".
        blob = {"props": {"pageProps": {"initialData": {"searchResult": {"itemStacks": [
            {"items": [
                {"usItemId": "1000000003", "name": "Garlic Powder Demo",
                 "priceInfo": {"itemPrice": "", "linePrice": "",
                               "linePriceDisplay": "", "minPrice": 0},
                 "availabilityStatus": "IN_STOCK", "canAddToCart": True},
            ]},
        ]}}}}}
        rows = products_from_next_data(blob)
        assert rows[0]["price"] is None
        assert rows[0]["price_text"] == ""

    def test_the_newer_price_shape_is_read_too(self):
        blob = {"props": {"pageProps": {"initialData": {"searchResult": {"itemStacks": [
            {"items": [
                {"usItemId": "1000000004", "name": "Sweet Paprika Demo",
                 "priceInfo": {"itemPrice": "3.48", "linePrice": "",
                               "linePriceDisplay": ""},
                 "availabilityStatus": "IN_STOCK", "canAddToCart": True},
            ]},
        ]}}}}}
        rows = products_from_next_data(blob)
        assert rows[0]["price"] == 3.48
        assert rows[0]["price_text"] == "3.48"

    def test_gzipped_bodies_are_read(self):
        # The store answers identity-encoded requests with its bot wall
        # (HTTP 412 live, 2026-09-30) and gzips the ones it accepts.
        import gzip as _gzip

        class _Headers(dict):
            def get_content_charset(self):
                return "utf-8"

        class _Resp:
            def __init__(self):
                self.headers = _Headers({"Content-Encoding": "gzip"})

            def read(self):
                return _gzip.compress(b"<html>hi</html>")

        assert WalmartHTTP._read_body(_Resp()) == "<html>hi</html>"

    def test_the_socks_env_is_parsed_or_refused(self, monkeypatch):
        from meal_to_cart.walmart import socks_proxy_from_env
        monkeypatch.delenv("MTC_SOCKS", raising=False)
        assert socks_proxy_from_env() is None
        monkeypatch.setenv("MTC_SOCKS", "127.0.0.1:1080")
        assert socks_proxy_from_env() == ("127.0.0.1", 1080)
        monkeypatch.setenv("MTC_SOCKS", "not-a-port")
        with pytest.raises(ValueError):
            socks_proxy_from_env()


class TestScoring:
    def test_a_plain_in_stock_match_is_added(self):
        result = score(Buy(item="olive oil", buy="2 teaspoon"), "olive oil",
                       [_row("Olive Oil Demo Brand, 1 Count")])
        assert result.action == "add"
        assert result.confidence >= THRESHOLD
        assert result.item_id == "1"

    def test_the_lines_own_word_is_not_a_form_change(self):
        # "garlic powder" is not a powdered form of garlic; it is the thing.
        result = score(Buy(item="garlic powder", buy="1 teaspoon"),
                       "garlic powder", [_row("Garlic Powder Demo Brand")])
        assert result.action == "add"

    def test_a_form_change_falls_under_the_threshold(self):
        result = score(Buy(item="onion", buy="1"), "onion",
                       [_row("Onion Powder Demo Brand")])
        assert result.action == "flag"
        assert "form" in result.reason

    def test_out_of_stock_never_gets_added(self):
        result = score(Buy(item="olive oil", buy="1"), "olive oil",
                       [_row("Olive Oil Demo", stock="OUT_OF_STOCK",
                             out_of_stock=True)])
        assert result.action == "flag"

    def test_an_empty_shelf_is_said_not_guessed(self):
        result = score(Buy(item="olive oil", buy="1"), "olive oil", [])
        assert result.action == "flag"
        assert "empty" in result.reason


class _FakeHTTP:
    """The search is the one edge; in tests it is held still."""

    def __init__(self, rows_by_query, fail=()):
        self.rows_by_query = rows_by_query
        self.fail = set(fail)
        self.queries: list[str] = []

    async def search(self, query, limit=5):
        self.queries.append(query)
        if query in self.fail:
            raise OSError("boom")
        return self.rows_by_query.get(query, [])


class TestBuildPlan:
    def test_every_answer_is_stamped_onto_its_own_line(self):
        lines = [Buy(item="olive oil", buy="2 teaspoon"),
                 Buy(item="kosher salt", buy="1 teaspoon")]
        http = _FakeHTTP({"olive oil": [_row("Olive Oil Demo")],
                          "kosher salt": [_row("Kosher Salt Demo")]})
        results = asyncio.run(cart.build_plan(lines, http))
        assert [result.buy for result in results] == lines
        assert all(result.buy is line for result, line in zip(results, lines))
        assert all(result.action == "add" for result in results)

    def test_a_failed_search_stays_visible_in_the_reason(self):
        lines = [Buy(item="olive oil", buy="1")]
        results = asyncio.run(cart.build_plan(lines, _FakeHTTP({}, fail=["olive oil"])))
        assert results[0].action == "flag"
        assert "failed" in results[0].reason
        assert "boom" in results[0].reason

    def test_a_throttled_search_is_retried_once(self):
        class Throttled(Exception):
            code = 429

        class BusyShelf(_FakeHTTP):
            def __init__(self, rows):
                super().__init__(rows)
                self.calls = 0

            async def search(self, query, limit=5):
                self.calls += 1
                if self.calls == 1:
                    raise Throttled("HTTP Error 429: Too Many Requests")
                return await super().search(query, limit=limit)

        cart._RETRY_WAIT = 0.01
        lines = [Buy(item="olive oil", buy="1")]
        http = BusyShelf({"olive oil": [_row("Olive Oil Demo")]})
        results = asyncio.run(cart.build_plan(lines, http))
        assert http.calls == 2
        assert results[0].action == "add"

    def test_a_walled_search_is_retried_and_can_still_resolve(self):
        # The bot wall (a /blocked redirect, no data blob) is a lottery, not
        # a verdict: the same request usually passes on a later try.
        class WalledShelf(_FakeHTTP):
            def __init__(self, rows):
                super().__init__(rows)
                self.calls = 0

            async def search(self, query, limit=5):
                self.calls += 1
                if self.calls == 1:
                    raise StorePageError("no __NEXT_DATA__ blob")
                return await super().search(query, limit=limit)

        cart._RETRY_WAIT = 0.01
        lines = [Buy(item="olive oil", buy="1")]
        http = WalledShelf({"olive oil": [_row("Olive Oil Demo")]})
        results = asyncio.run(cart.build_plan(lines, http))
        assert http.calls == 2
        assert results[0].action == "add"

    def test_a_search_walled_every_time_is_flagged_not_guessed(self):
        calls = {"n": 0}

        class AlwaysWalled(_FakeHTTP):
            async def search(self, query, limit=5):
                calls["n"] += 1
                raise StorePageError("no __NEXT_DATA__ blob")

        cart._RETRY_WAIT = 0.01
        lines = [Buy(item="olive oil", buy="1")]
        results = asyncio.run(cart.build_plan(lines, AlwaysWalled({})))
        assert calls["n"] == cart._WALL_ATTEMPTS
        assert results[0].action == "flag"
        assert "failed" in results[0].reason

    def test_the_gap_is_kept_between_lines_when_asked(self):
        import time
        lines = [Buy(item="olive oil", buy="1"),
                 Buy(item="kosher salt", buy="1")]
        http = _FakeHTTP({"olive oil": [_row("Olive Oil Demo")],
                          "kosher salt": [_row("Kosher Salt Demo")]})
        cart._SEARCH_GAP = 0.05
        start = time.monotonic()
        results = asyncio.run(cart.build_plan(lines, http))
        assert time.monotonic() - start >= 0.05
        assert all(result.action == "add" for result in results)
