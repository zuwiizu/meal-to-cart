"""The store's own search page, read the way the store publishes it.

No browser, no scraper service, no model: walmart.com ships its search
results as one embedded __NEXT_DATA__ JSON blob (the site is a Next.js
app), and that blob is the only thing read here. It exists to be
machine-read, which is what makes this leg deterministic instead of a fight
with markup -- and when the blob is absent, this module RAISES instead of
guessing from the visible page, because guessing what a store sells is how
wrong carts get built.

The user-agent is a browser's own. A reader that announces itself as a
personal tool still has to look like the browser the store serves, or the
bot wall answers instead; the honesty lives in the code (one GET per query,
no crawling, no login), not in a header the wall ignores.
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
SEARCH_URL = "https://www.walmart.com/search?q={query}"
NEXT_DATA = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S | re.I)


class StorePageError(RuntimeError):
    """The store's page did not carry the published data blob."""


def _items(data: dict) -> list[dict]:
    """Every product tile in the embedded search result, in page order."""
    try:
        page = data["props"]["pageProps"]
    except (KeyError, TypeError):
        return []
    result = page.get("initialData", {}).get("searchResult") or {}
    out: list[dict] = []
    seen: set[str] = set()
    for stack in result.get("itemStacks") or []:
        for tile in stack.get("items") or []:
            item_id = str(tile.get("usItemId") or "").strip()
            if item_id and item_id not in seen:
                seen.add(item_id)
                out.append(tile)
    return out


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def products_from_next_data(data: dict, limit: int = 0) -> list[dict]:
    """Product rows in this repo's one shape, from the embedded search blob.

    promises_known is the honesty flag: a tile that said nothing about
    delivery must never be read as a tile that promised nothing, so "not
    parsed" and "parsed and empty" are different states, and the scorer
    treats them differently.
    """
    rows: list[dict] = []
    for tile in _items(data):
        item_id = str(tile.get("usItemId") or "").strip()
        if not item_id:
            continue
        price_info = tile.get("priceInfo") or {}
        current = price_info.get("currentPrice") or {}
        promises = {}
        for key in ("fulfillment", "shippingAndPickup", "fulfillmentSummary"):
            value = tile.get(key)
            if isinstance(value, dict) and value:
                promises = value
                break
        stock = str(tile.get("availabilityStatus") or tile.get("stock") or "")
        rows.append({
            "title": str(tile.get("name") or ""),
            "price": _num(current.get("price")),
            "price_text": str(current.get("priceString") or ""),
            "item_id": item_id,
            "rating": str(tile.get("averageRating") or ""),
            "url": f"/ip/{item_id}",
            "sponsored": bool(tile.get("isSponsoredFlag")
                              or tile.get("sponsored")),
            "seller": str(tile.get("sellerName") or ""),
            "fulfillment": str(tile.get("fulfillmentBadge") or ""),
            "store_ids": list(tile.get("storeIds") or []),
            "pickup": bool(tile.get("pickup")),
            "delivery_dates": list(tile.get("deliveryDates") or []),
            "promises": promises,
            "promises_known": bool(promises),
            "unit_price": str((price_info.get("unitPrice") or {}).get(
                "priceString", "")) if isinstance(
                    price_info.get("unitPrice"), dict) else "",
            "stock": stock,
            "out_of_stock": "OUT_OF_STOCK" in stock.upper(),
            "can_add_to_cart": bool(tile.get("canAddToCart", True)),
        })
        if limit and len(rows) >= limit:
            break
    return rows


class WalmartHTTP:
    """The live search: one GET, one embedded JSON, one list of rows."""

    def __init__(self, timeout: float = 20.0, user_agent: str = UA):
        self.timeout = timeout
        self.user_agent = user_agent

    def _fetch(self, url: str) -> str:
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def _blob(self, html: str) -> dict:
        match = NEXT_DATA.search(html or "")
        if not match:
            raise StorePageError(
                "the store's page carried no __NEXT_DATA__ blob: either the "
                "markup changed or this request met the bot wall, and this "
                "module will not guess products out of visible markup")
        try:
            return json.loads(match.group(1))
        except ValueError as exc:
            raise StorePageError(f"the store's embedding was not JSON: {exc}")

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """This query's product rows, in page order."""
        url = SEARCH_URL.format(
            query=urllib.parse.quote_plus(str(query or "")))
        html = await asyncio.to_thread(self._fetch, url)
        return products_from_next_data(self._blob(html), limit=limit)
