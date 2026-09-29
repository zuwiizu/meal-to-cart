"""The profile's own dietary rules, applied the way it stated them.

Severities are the whole contract: "reject" bars a recipe from a plan,
"review" only flags it for a human. Tokens match whole words in a recipe's
title and its ingredients; exceptions are phrases that scrub a token where
the phrase covers it -- a rule about wine does not reject the wine vinegar a
recipe legitimately deglazes with, but it still rejects the wine.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

REJECT = "reject"
REVIEW = "review"
OK = "ok"


@dataclass(frozen=True)
class Verdict:
    title: str
    status: str
    rule: str = ""
    why: str = ""

    def explain(self) -> str:
        """The one-line reason a person reads."""
        if self.status == OK:
            return "no rule applied"
        return f"{self.rule}: {self.why}" if self.why else self.rule


def _haystacks(recipe: dict) -> list[str]:
    """Every text a rule may look at: the title and each ingredient line."""
    out = [str(recipe.get("title") or "")]
    for ingredient in recipe.get("ingredients") or []:
        if isinstance(ingredient, dict):
            out.append(str(ingredient.get("item") or ""))
        else:
            out.append(str(ingredient))
    return [text for text in out if text.strip()]


def _spans(text: str, phrases: list[str]) -> list[tuple[int, int]]:
    spans = []
    for phrase in phrases:
        for match in re.finditer(re.escape(phrase), text):
            spans.append(match.span())
    return spans


def _scrubbed(start: int, end: int, scrub: list[tuple[int, int]]) -> bool:
    """True when an exception phrase covers the token's own span."""
    return any(s <= start and end <= e for s, e in scrub)


class Ruleset:
    def __init__(self, rules: list | None = None):
        self.rules = [
            rule for rule in (rules or [])
            if isinstance(rule, dict) and rule.get("tokens")
        ]

    @classmethod
    def load(cls, path) -> "Ruleset":
        """The rules file as written, or an empty ruleset when there is none.

        An absent file is a profile that stated no rules -- and an empty
        gate is that fact read honestly. A file that cannot be parsed
        raises: a slot that only looks filled must not read as filled.
        """
        path = Path(path)
        if not path.is_file():
            return cls([])
        data = json.loads(path.read_text())
        rows = data.get("rules") if isinstance(data, dict) else data
        return cls(list(rows or []))

    def evaluate(self, recipe: dict) -> Verdict:
        """This recipe under this ruleset: ok, review, or rejected.

        A reject wins immediately; a review is remembered and returned only
        when nothing stronger fired, so a recipe cannot be both flagged and
        barred with the weaker word.
        """
        title = str(recipe.get("title") or "").strip()
        haystacks = [text.lower() for text in _haystacks(recipe)]
        review: Verdict | None = None
        for rule in self.rules:
            name = str(rule.get("name") or "rule")
            severity = str(rule.get("severity") or REVIEW).lower()
            why = str(rule.get("why") or "")
            exceptions = [str(e).lower() for e in rule.get("exceptions") or []]
            for text in haystacks:
                scrub = _spans(text, exceptions)
                for token in rule.get("tokens") or []:
                    token = str(token).strip().lower()
                    if not token:
                        continue
                    for match in re.finditer(r"\b" + re.escape(token) + r"\b",
                                             text):
                        start, end = match.span()
                        if _scrubbed(start, end, scrub):
                            continue
                        if severity == REJECT:
                            return Verdict(title, REJECT, name, why)
                        if review is None:
                            review = Verdict(title, REVIEW, name, why)
        return review or Verdict(title, OK)
