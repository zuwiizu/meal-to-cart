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
import contextlib
import gzip
import json
import os
import re
import socket
import urllib.parse
import urllib.request
import zlib

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
SEARCH_URL = "https://www.walmart.com/search?q={query}"
NEXT_DATA = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S | re.I)


def socks_proxy_from_env() -> tuple[str, int] | None:
    """MTC_SOCKS=host:port, or None when unset.

    The supported way to shop through the network of the machine that owns
    the store account when THIS host's own address is the one the store has
    flagged: every store request then leaves through that SOCKS5 proxy.
    """
    raw = (os.environ.get("MTC_SOCKS") or "").strip()
    if not raw:
        return None
    host, _, port = raw.rpartition(":")
    try:
        return (host or "127.0.0.1", int(port))
    except ValueError as exc:
        raise ValueError(f"MTC_SOCKS is not host:port: {raw!r}") from exc


@contextlib.contextmanager
def via_socks(proxy: tuple[str, int]):
    """Route new sockets through PySocks for one fetch.

    Sequential callers only: the swap is process-wide while it is held, so
    concurrent fetches in other threads would also take this path.
    """
    import socks  # PySocks: imported only when a proxy is asked for
    host, port = proxy
    socks.set_default_proxy(socks.SOCKS5, host, port, rdns=True)
    saved = socket.socket
    socket.socket = socks.socksocket
    try:
        yield
    finally:
        socket.socket = saved


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
        # Prices move off the search blob at times (seen live 2026-09-30:
        # every tile's priceInfo present but empty, no currentPrice); the
        # first non-empty shape wins, and an empty price is None, never 0,
        # so the week's total can say which lines it covers.
        price = _num(current.get("price"))
        price_text = str(current.get("priceString") or "")
        if price is None:
            for key in ("itemPrice", "linePrice"):
                candidate = price_info.get(key)
                if isinstance(candidate, dict):
                    price = _num(candidate.get("price"))
                    price_text = price_text or str(candidate.get("priceString") or "")
                else:
                    price = _num(candidate)
                    price_text = price_text or (str(candidate) if price is not None else "")
                if price is not None:
                    break
        promises = {}
        for key in ("fulfillment", "shippingAndPickup", "fulfillmentSummary"):
            value = tile.get(key)
            if isinstance(value, dict) and value:
                promises = value
                break
        stock = str(tile.get("availabilityStatus") or tile.get("stock") or "")
        rows.append({
            "title": str(tile.get("name") or ""),
            "price": price,
            "price_text": price_text,
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

    @staticmethod
    def _read_body(response) -> str:
        """The response's text, decompressed when the store gzipped it.

        The store answers identity-encoded requests with its bot wall (seen
        live 2026-09-30: HTTP 412 without an Accept-Encoding header, HTTP 200
        with one) -- so the accept-encoding below is part of the same honesty
        the module's User-Agent note explains, and the decoding lands here.
        """
        raw = response.read()
        encoding = (response.headers.get("Content-Encoding") or "").lower()
        if encoding == "gzip":
            raw = gzip.decompress(raw)
        elif encoding == "deflate":
            raw = zlib.decompress(raw)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")

    def _fetch(self, url: str) -> str:
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        })
        proxy = socks_proxy_from_env()
        if proxy is None:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return self._read_body(response)
        with via_socks(proxy):
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return self._read_body(response)

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
