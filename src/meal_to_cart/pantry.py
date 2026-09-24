"""Ask about the things most kitchens already have, once, and remember.

The planner's own cupboard check is a fixed list of seasonings that it prints and
then ignores: the shopping list still contains every one of them. So the same
spices get bought every week, or the reader deletes them by hand every week.

This asks about only the items this week's plan actually needs, and persists the
answers, so the second week is silent and the list is right.

Defaults matter more than they look. With no stored answer, a spice is treated as
"you probably have it" and stays off the list; anything you said you need stays
on it even if it is a spice.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Buy
from .normalize import canonical
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data" / "pantry.default.json"


def load_catalog(path: str | Path | None = None) -> dict[str, list[str]]:
    """normalised item -> group name, so a line can be traced to its shelf."""
    data = json.loads(Path(path or CATALOG).read_text())
    lookup: dict[str, list[str]] = {}
    for group in data["groups"]:
        for item in group["items"]:
            lookup.setdefault(canonical(item), []).append(group["name"])
    return lookup


def candidates(buys: list[Buy], catalog: dict[str, list[str]],
               known: dict[str, str] | None = None) -> list[Buy]:
    """The lines worth asking about: on this week's list, and a known staple.

    Anything already answered is skipped, which is what makes the second run
    silent.
    """
    known = known or {}
    seen: set[str] = set()
    out: list[Buy] = []
    for buy in buys:
        key = canonical(buy.item)
        if key in seen or key not in catalog or key in known:
            continue
        seen.add(key)
        out.append(buy)
    return out


def group_for(item: str, catalog: dict[str, list[str]]) -> str:
    groups = catalog.get(canonical(item))
    return groups[0] if groups else "Other"


def filter_buys(buys: list[Buy], store: Store) -> tuple[list[Buy], list[Buy]]:
    """Split into (still to buy, already have) using stored answers."""
    known = store.pantry()
    keep: list[Buy] = []
    have: list[Buy] = []
    for buy in buys:
        if known.get(canonical(buy.item)) == "have":
            have.append(buy)
        else:
            keep.append(buy)
    return keep, have
