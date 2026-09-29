"""Does the row the search found deserve the line? A score, not a guess.

Deterministic and explainable, because a cart is a money decision: the
score is built from things a person can check -- does the title carry the
words the line asked for, is it in stock, is it the same form of the thing
(powdered against fresh), is the pack an obviously wrong size. No model runs
here, and nothing here talks to the network; it is handed rows and it
answers.

The honest half is what is MISSING from a row: when the page said nothing
about delivery, that earns no bonus (it is not a promise of anything), and
when no row clears the threshold, the reason says why the best candidate
did not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalize_query

THRESHOLD = 0.70

# A title advertising one of these has changed what the line is -- unless
# the line asked for that word itself ("garlic powder" is not a powdered
# form of "garlic"; it is exactly the thing).
_FORM_WORDS = ("powder", "dried", "frozen", "canned", "mix", "flavored",
               "candy", "snack", "chips")
# Bulk sizes are a different purchase than the week asked for. Single words
# are matched as whole words -- "case" must not fire inside "casero" -- and
# the multi-word forms as phrases, because a person reading the tile sees a
# phrase and the scorer should too.
_BULK_WORDS = ("case", "bundle", "bulk")
_BULK_PHRASES = ("pack of", "family size", "party size")
_WORD = re.compile(r"[a-z0-9']+")


def _stem(word: str) -> str:
    """A naive, symmetric plural fold: both sides of a comparison take it,
    so exact equality still holds and 'lemons' meets 'lemon'."""
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(word) for word in _WORD.findall(str(text or "").lower())]


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    """Is needle a consecutive run inside haystack? Word-by-word, so the
    comma in 'Garlic Powder, 3.4 oz' cannot hide the phrase."""
    if not needle or len(needle) > len(haystack):
        return False
    return any(haystack[i:i + len(needle)] == needle
               for i in range(len(haystack) - len(needle) + 1))


@dataclass
class MatchResult:
    """One line's answer from the store's search.

    buy carries the SAME object that was handed to build_plan, so a caller
    can pair answers to lines by identity and never by guesswork.
    """
    buy: object
    query: str
    item_id: str | None = None
    title: str = ""
    price_text: str = ""
    price: float | None = None
    confidence: float = 0.0
    action: str = "flag"          # "add" | "flag"
    reason: str = ""


def _score_row(query: str, row: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    title = normalize_query(str(row.get("title") or ""))
    if not title:
        return 0.0, ["no title to judge"]
    score = 0.0
    query_words = _tokens(query)
    title_words = _tokens(title)
    if _contains_run(title_words, query_words):
        score += 0.72
    else:
        hit = [word for word in query_words if word in title_words]
        if query_words and len(hit) == len(query_words):
            score += 0.67
        elif hit:
            score += 0.25 * (len(hit) / len(query_words))
            notes.append("only part of the line's own words are in the title")
        else:
            return 0.0, ["the title does not carry the line's words"]
    for word in _FORM_WORDS:
        if _stem(word) in title_words and word not in query:
            score -= 0.2
            notes.append("a different form of the thing")
            break
    bulk = (any(_stem(word) in title_words for word in _BULK_WORDS)
            or any(phrase in title for phrase in _BULK_PHRASES))
    if bulk and not any(word in query for word in _BULK_WORDS):
        score -= 0.25
        notes.append("a bulk pack")
    if row.get("out_of_stock"):
        score -= 0.4
        notes.append("out of stock")
    elif str(row.get("stock") or "").upper() == "IN_STOCK":
        score += 0.05
    if row.get("can_add_to_cart"):
        score += 0.05
    if str(row.get("seller") or "") == "Walmart.com":
        score += 0.03
    if row.get("sponsored"):
        score -= 0.05
        notes.append("a sponsored tile")
    if row.get("promises_known"):
        score += 0.03
    return max(0.0, min(score, 0.95)), notes


def score(buy, query: str, rows: list[dict]) -> MatchResult:
    """The line's own verdict: the best row, or a reason it stayed unadded."""
    best: tuple[float, dict, list[str]] | None = None
    for row in rows or []:
        value, notes = _score_row(query, row)
        if best is None or value > best[0]:
            best = (value, row, notes)
    if best is None:
        return MatchResult(
            buy=buy, query=query, action="flag",
            reason=f"the search for {query!r} came back empty")
    value, row, notes = best
    if value >= THRESHOLD and row.get("item_id"):
        return MatchResult(
            buy=buy, query=query, item_id=str(row.get("item_id")),
            title=str(row.get("title") or ""),
            price_text=str(row.get("price_text") or ""),
            price=row.get("price"), confidence=round(value, 2),
            action="add", reason=f"matched on {query!r} at {value:.2f}")
    detail = "; ".join(notes) if notes else "no candidate was close enough"
    return MatchResult(
        buy=buy, query=query, confidence=round(value, 2), action="flag",
        reason=(f"the best candidate for {query!r} scored {value:.2f}, "
                f"under {THRESHOLD:.2f}: {detail}"))
