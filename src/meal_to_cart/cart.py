"""The agent loop: propose, ask, then write.

Nothing in this module reaches the network on its own. build_plan only searches.
apply() is the only function that writes to a cart, and it refuses to write
anything a human did not approve.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from .match import score
from .models import Buy, MatchResult
from .normalize import normalize_query
from .walmart import WalmartBlocked

Approver = Callable[[MatchResult], bool]

# Walmart answers a burst of searches with its bot wall. Waiting is not enough:
# the block is sticky for the life of one browser session, and the server keeps
# saving the block page's cookies. Rotating the session is what actually clears
# it, so a retry means a new browser, not a longer pause.
BLOCK_ATTEMPTS = 3
BLOCK_BACKOFF = 5.0


async def _search_with_retry(matcher, query: str, limit: int = 5) -> list[dict]:
    import asyncio

    last: Exception | None = None
    for attempt in range(BLOCK_ATTEMPTS):
        try:
            return await matcher.search(query, limit=limit)
        except WalmartBlocked as exc:
            last = exc
            if attempt < BLOCK_ATTEMPTS - 1:
                if hasattr(matcher, "restart"):
                    await matcher.restart()
                await asyncio.sleep(BLOCK_BACKOFF * (attempt + 1))
    raise last if last else RuntimeError("unreachable")


async def build_plan(buys: list[Buy], matcher,
                     on_progress: Callable[[int, int, MatchResult], None] | None = None,
                     pause: float = 0.0) -> list[MatchResult]:
    """Search only -- this function cannot write to a cart.

    `pause` throttles the search loop. Walmart's bot detection answers a rapid
    burst of queries with its block page, so a full 45-item run paces itself.
    """
    import asyncio

    results: list[MatchResult] = []
    total = len(buys)
    for index, buy in enumerate(buys, start=1):
        query = normalize_query(buy.item)
        if not query:
            continue
        try:
            candidates = await _search_with_retry(matcher, query)
            result = score(buy, query, candidates)
        except Exception as exc:  # noqa: BLE001 - one bad line must not end the run
            result = MatchResult(buy=buy, query=query, action="flag",
                                 reason=f"search failed: {type(exc).__name__}")
        results.append(result)
        if on_progress:
            on_progress(index, total, result)
        if pause:
            await asyncio.sleep(pause)
    return results


async def apply(results: list[MatchResult], gateway, approve: Approver,
                dry_run: bool = False) -> dict:
    summary = {"would_add": 0, "added": 0, "denied": 0, "skipped_flagged": 0}
    for result in results:
        if result.action != "add" or not result.item_id:
            summary["skipped_flagged"] += 1
            continue
        if dry_run:
            summary["would_add"] += 1
            continue
        if not approve(result):
            summary["denied"] += 1
            continue
        await gateway.add(result.item_id, 1)
        summary["added"] += 1
    return summary


def render(results: list[MatchResult]) -> str:
    lines = []
    for r in sorted(results, key=lambda x: (x.action != "add", x.buy.aisle, x.buy.item)):
        price = f"${r.price:.2f}" if r.price is not None else "     ?"
        note = r.title[:46] if r.title else f"({r.reason})"
        lines.append(f"[{r.action:4}] {r.confidence:.2f} {price:>7}  "
                     f"{normalize_query(r.buy.item):32.32} -> {note}")
    return "\n".join(lines)
