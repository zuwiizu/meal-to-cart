"""Shared types.

Field names mirror the pipeline's own shopping.json so the boundary needs no
translation layer. A real line looks like:

    {"item": "tablespoon fresh chives", "buy": "1 bunch",
     "aisle": "produce", "meals": ["Thursday"], "need": "a garnish",
     "approximate": true, "spare": ""}
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Buy:
    item: str
    buy: str = ""
    aisle: str = ""
    meals: list[str] = field(default_factory=list)
    need: str = ""
    approximate: bool = False
    spare: str = ""
    source: str = "plan"          # "plan" | "extras"


@dataclass
class MatchResult:
    buy: Buy
    query: str
    item_id: str | None = None
    title: str = ""
    price_text: str = ""
    price: float | None = None
    confidence: float = 0.0
    action: str = "flag"          # "add" | "flag"
    reason: str = ""
