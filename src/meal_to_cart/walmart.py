"""The single place that speaks MCP to the Walmart server.

Every path here is scoped inside the project. Each tool in the chain assumes it
owns the user's home directory, and this agent runs under a file sandbox that
only writes to the workspace:

  * bun    -- "unable to write files to tempdir: PermissionDenied" without TMPDIR
  * bun    -- cannot install a package it cannot cache, so BUN_INSTALL_CACHE_DIR
  * patchright -- would put a 550MB browser in ~/Library/Caches
  * the MCP server -- hardcodes os.homedir()/.striderlabs/walmart (dist/session.js)
    for its cookie jar, and Node resolves HOME first

scripts/setup_mcp.sh sets the same four, so setup and runtime agree.

The server answers search with formatted text, not JSON:

    Found 3 products for "feta cheese":

    1. Frigo Crumbled Feta Cheese, 5 oz Refrigerated Plastic Cup
       Price: $3.28
       Item ID: 34729673
       Rating: 4.7 out of 5 stars
       URL: https://www.walmart.com/ip/...

so parsing it is this module's job. Nothing above this layer sees text.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache"
ENTRY = (ROOT / "vendor" / "walmart-mcp" / "node_modules" / "@striderlabs"
         / "mcp-walmart" / "dist" / "index.js")
COOKIES = CACHE / "home" / ".striderlabs" / "walmart" / "cookies.json"

# Emitted by the patched server (see scripts/patch_mcp.py) when the page is
# Walmart's bot wall rather than a product grid.
BLOCK_MARKER = "BLOCKED_BY_WALMART"

_PRODUCT = re.compile(
    r"^\s*\d+\.\s+(?P<title>.+?)(?:\s*\[Sponsored\])?\s*\n"
    r"\s*Price:\s*(?P<price>[^\n]*)\n"
    r"\s*Item ID:\s*(?P<item_id>[^\n]*)\n"
    r"\s*Rating:\s*(?P<rating>[^\n]*)\n"
    r"\s*URL:\s*(?P<url>[^\n]*)",
    re.M,
)


class WalmartBlocked(RuntimeError):
    """Walmart served the bot wall. The session cookie jar is poisoned."""


def mcp_env() -> dict[str, str]:
    for sub in ("tmp", "bun", "ms-playwright", "home"):
        (CACHE / sub).mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "BUN_INSTALL_CACHE_DIR": str(CACHE / "bun"),
        "TMPDIR": str(CACHE / "tmp"),
        "PLAYWRIGHT_BROWSERS_PATH": str(CACHE / "ms-playwright"),
        "HOME": str(CACHE / "home"),
    }


def server_params() -> StdioServerParameters:
    if not ENTRY.exists():
        raise RuntimeError(f"the Walmart MCP server is not installed at {ENTRY}\n"
                           "run scripts/setup_mcp.sh first")
    return StdioServerParameters(command="node", args=[str(ENTRY)], env=mcp_env())


def reset_session() -> bool:
    """Delete the saved cookie jar. Returns True if something was deleted.

    A blocked page still gets its cookies saved, and those cookies carry the
    block fingerprint (_pxvid, pxcts, btc, bsc, vtc), so every later run
    reloads the block. Measured: with a poisoned jar every search lands on
    /blocked?uuid=...; after deleting the file the next search returns real
    products.
    """
    if COOKIES.exists():
        COOKIES.unlink()
        return True
    return False


def _text(result: Any) -> str:
    return "\n".join(
        p for p in (getattr(c, "text", "") for c in getattr(result, "content", [])) if p
    )


def parse_search(text: str) -> list[dict]:
    """Turn the server's product listing into dicts."""
    if not text:
        return []
    if "No products found" in text:
        return []
    found = []
    for match in _PRODUCT.finditer(text):
        price_text = match.group("price").strip()
        number = re.search(r"\d+(?:\.\d+)?", price_text)
        price = float(number.group()) if number else None
        item_id = match.group("item_id").strip()
        found.append({
            "title": match.group("title").strip(),
            "price_text": price_text,
            "price": price,
            # The server renders a missing ID as the literal "N/A".
            "item_id": None if item_id in ("", "N/A") else item_id,
            "rating": match.group("rating").strip(),
            "url": match.group("url").strip(),
        })
    return found


class WalmartMCP:
    """Async context manager holding one stdio session for the whole run."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "WalmartMCP":
        read, write = await self._stack.enter_async_context(stdio_client(server_params()))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def call(self, tool: str, args: dict) -> Any:
        assert self.session is not None, "session not started"
        return _text(await self.session.call_tool(tool, args))

    async def restart(self) -> None:
        """Drop the browser session and the cookie jar, then reconnect.

        A block is sticky for the life of one browser session: the same block
        uuid comes back on every retry, as this run's log shows twice for the
        same query. Waiting does not clear it and the cookie jar actively
        preserves it. A new browser with a clean jar is what clears it.
        """
        try:
            await self._stack.aclose()
        finally:
            self._stack = AsyncExitStack()
            reset_session()
            await self.__aenter__()

    async def status(self) -> str:
        return await self.call("status", {})

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search and parse. Raises WalmartBlocked so the caller can recover."""
        raw = await self.call("search", {"query": query, "limit": limit})
        if BLOCK_MARKER in raw:
            raise WalmartBlocked(query)
        return parse_search(raw)

    async def add(self, item_id: str, quantity: int = 1) -> str:
        return await self.call("add_to_cart", {"item_id": item_id, "quantity": quantity})

    async def view_cart(self) -> str:
        return await self.call("view_cart", {})
