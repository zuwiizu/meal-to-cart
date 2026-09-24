"""Score Walmart search candidates against a normalised query.

Pure functions. No network, no browser, no session -- which is what makes the
matching logic testable at all, given everything underneath it needs a login
and a 550MB browser.

The rule that matters: when nothing scores well enough, flag it for a human
instead of adding the closest guess. A wrong item in a grocery cart costs more
than a question.
"""
from __future__ import annotations

import re

from .models import Buy, MatchResult
from .normalize import pack_hint

AUTO_ADD_THRESHOLD = 0.70

_STOP = {"the", "and", "with", "of", "a", "an", "oz", "lb", "lbs", "pack",
         "count", "ct", "fresh", "frozen", "each"}

_BULK_SIZE = re.compile(r"\b(16|24|32|48|64|80|128)\s*(?:oz|fl oz|ct|count)\b", re.I)

# A one-word query matches any title containing that word. In a real run, "dill"
# scored 1.00 against "OH SNAP! Dilly Bites Dill Pickle Snack Pack, Fat Free" --
# a perfect score for a bag of candy when the plan wanted a bunch of herbs.
# When the query does not itself name a product form, a title that does is a
# different kind of thing, however many tokens it shares.
FORM_WORDS = {
    "snack", "snacks", "chips", "candy", "soda", "juice", "sauce", "dressing",
    "pickle", "pickles", "pickled", "flavored", "flavour", "mix", "seasoning",
    "powder", "cereal", "bar", "bars", "cookie", "cookies", "cracker", "crackers",
    "frozen", "instant", "dip", "spread", "syrup", "jam", "jelly", "canned",
}
FORM_MISMATCH_PENALTY = 0.45


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


def confidence(query: str, title: str, buy: Buy) -> float:
    wanted = _tokens(query)
    if not wanted:
        return 0.0
    title_tokens = _tokens(title)
    overlap = len(wanted & title_tokens) / len(wanted)
    penalty = 0.0
    # A recipe asking for half a cup should not get a 64oz club pack.
    if pack_hint(buy.buy) == "small" and _BULK_SIZE.search(title):
        penalty += 0.15
    # The query did not ask for a processed form, but the product is one.
    if not (wanted & FORM_WORDS) and (title_tokens & FORM_WORDS):
        penalty += FORM_MISMATCH_PENALTY
    return max(0.0, min(1.0, overlap - penalty))


def score(buy: Buy, query: str, candidates: list[dict]) -> MatchResult:
    if not candidates:
        return MatchResult(buy=buy, query=query, action="flag",
                           reason="no search results")
    best: dict | None = None
    best_conf = 0.0
    for candidate in candidates:
        conf = confidence(query, str(candidate.get("title", "")), buy)
        if conf > best_conf:
            best, best_conf = candidate, conf
    if best is None:
        return MatchResult(buy=buy, query=query, action="flag",
                           reason="nothing scored above zero")
    item_id = best.get("item_id")
    if not item_id:
        return MatchResult(buy=buy, query=query, action="flag",
                           reason="best match has no item id")
    action = "add" if best_conf >= AUTO_ADD_THRESHOLD else "flag"
    return MatchResult(
        buy=buy,
        query=query,
        item_id=str(item_id),
        title=str(best.get("title", "")),
        price_text=str(best.get("price_text", "")),
        price=best.get("price") if isinstance(best.get("price"), float) else None,
        confidence=round(best_conf, 2),
        action=action,
        reason="" if action == "add" else f"only {best_conf:.2f} confident",
    )
