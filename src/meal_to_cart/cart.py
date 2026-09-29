"""Search each planned line, and let the scorer decide what came back.

This is the searching half of the seam: build_plan takes lines and a search
(anything with an async search(query, limit)), asks once per line, and
stamps every answer back ONTO the line it came from -- the same object, so
the caller can pair answers to lines by identity and never guess. A search
that fails leaves a flag with the failure in its reason, never a silent
hole.
"""
from __future__ import annotations

from .match import MatchResult, score
from .normalize import normalize_query


async def build_plan(lines: list, http) -> list[MatchResult]:
    """One MatchResult per line, in order, guaranteed."""
    results: list[MatchResult] = []
    for line in lines or []:
        query = normalize_query(str(getattr(line, "item", "") or ""))
        try:
            # Ten, not five: the store's opening tiles are its ad block, and
            # the real thing sits under it. Found live -- a five-tile shelf
            # flagged "lemon" while tile six was exactly the thing.
            rows = await http.search(query, limit=10)
        except Exception as exc:          # the search is the one flaky edge
            results.append(MatchResult(
                buy=line, query=query, action="flag",
                reason=f"the search for {query!r} failed: {exc}"))
            continue
        results.append(score(line, query, rows))
    return results
