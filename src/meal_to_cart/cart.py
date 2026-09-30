"""Search each planned line, and let the scorer decide what came back.

This is the searching half of the seam: build_plan takes lines and a search
(anything with an async search(query, limit)), asks once per line, and
stamps every answer back ONTO the line it came from -- the same object, so
the caller can pair answers to lines by identity and never guess. A search
that fails leaves a flag with the failure in its reason, never a silent
hole.
"""
from __future__ import annotations

import asyncio
import os

from .match import MatchResult, score
from .normalize import normalize_query
from .walmart import StorePageError

# The store's throttle answers 429; one short, bounded retry is the
# difference between a cart and a refused line on a busy connection. The
# wait is a module constant so a test can hold the network still and take
# it to zero.
_RETRY_WAIT = 2.5
_RETRYABLE = (429, 503)
# The store's bot wall is a lottery that clears with a steady pace: the
# same browser-shaped request comes back as the real page or as a redirect
# to /blocked, in bursts, and a ~25s spacing rides through it (seen live
# 2026-09-30: four walls 15s apart, then 3/3 passes at 25s). So: keep a gap
# between lines when the operator asks for one (MTC_SEARCH_GAP, seconds),
# and still retry a walled line a few times before calling it refused.
_SEARCH_GAP = float(os.environ.get("MTC_SEARCH_GAP", "0") or 0)
_WALL_ATTEMPTS = 4


async def _search(http, query: str):
    last_wall: Exception | None = None
    for attempt in range(_WALL_ATTEMPTS):
        try:
            return await http.search(query, limit=10)
        except StorePageError as exc:      # the wall: try again, then again
            last_wall = exc
            if attempt < _WALL_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_WAIT)
        except Exception as exc:           # only the store's own "try later"
            code = getattr(exc, "code", None)
            if code not in _RETRYABLE:
                raise
            await asyncio.sleep(_RETRY_WAIT)
            return await http.search(query, limit=10)
    assert last_wall is not None
    raise last_wall


async def build_plan(lines: list, http) -> list[MatchResult]:
    """One MatchResult per line, in order, guaranteed."""
    results: list[MatchResult] = []
    for index, line in enumerate(lines or []):
        if index and _SEARCH_GAP:
            await asyncio.sleep(_SEARCH_GAP)
        query = normalize_query(str(getattr(line, "item", "") or ""))
        try:
            # Ten, not five: the store's opening tiles are its ad block, and
            # the real thing sits under it. Found live -- a five-tile shelf
            # flagged "lemon" while tile six was exactly the thing.
            rows = await _search(http, query)
        except Exception as exc:          # the search is the one flaky edge
            results.append(MatchResult(
                buy=line, query=query, action="flag",
                reason=f"the search for {query!r} failed: {exc}"))
            continue
        results.append(score(line, query, rows))
    return results
