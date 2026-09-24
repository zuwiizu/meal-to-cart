"""Read the pipeline's shopping.json and the confirmed extras list.

The filter is deliberately narrow and aisle-driven. A word-based rule that
dropped anything containing "pepper" would throw away the green bell pepper,
which is a real vegetable two aisles over from the spice rack.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Buy
from .normalize import is_filler, normalize_query

# The pipeline already knows its own staples, and its own spices aisle is the
# "check the cupboard first" list it prints above the shopping list.
STAPLE_AISLES = {"spices"}

# The pipeline's own rule is 'aisle == "spices" or item in STAPLE_ITEMS', with
# exact string matching. That misses 'teaspoon kosher salt' and 'teaspoon
# allspice', which sit in the pantry aisle but are seasonings. Matching on the
# normalised name catches them. Anything not listed is a real purchase --
# 'green bell pepper' and 'lemon garlic butter' both survive on purpose.
SEASONINGS = {
    "salt", "kosher salt", "sea salt", "salt and pepper", "garlic salt",
    "pepper", "black pepper", "garlic pepper", "cayenne pepper", "white pepper",
    "allspice", "cumin", "cinnamon", "paprika", "oregano", "cardamom",
    "nutmeg", "turmeric", "coriander", "chili powder", "clove",
    "garlic powder", "onion powder", "italian seasoning blend", "seasoning",
    "olive oil", "extra virgin olive oil", "butter", "unsalted butter",
    "cooking spray",
}


def _is_buyable(item: str, aisle: str) -> bool:
    if not item.strip():
        return False
    if is_filler(item):
        return False
    if aisle.strip().lower() in STAPLE_AISLES:
        return False
    return normalize_query(item) not in SEASONINGS


def _row(raw: dict, source: str) -> Buy:
    return Buy(
        item=str(raw.get("item", "")).strip(),
        buy=str(raw.get("buy", "")),
        aisle=str(raw.get("aisle", "")),
        meals=list(raw.get("meals") or []),
        need=str(raw.get("need", "")),
        approximate=bool(raw.get("approximate", False)),
        spare=str(raw.get("spare", "")),
        source=source,
    )


def dedupe(buys: list[Buy]) -> list[Buy]:
    """Collapse lines that describe the same product.

    The pipeline emits both 'teaspoon cinnamon' and 'teaspoon cinnamon, ground',
    both 'buttermilk' and '1% buttermilk', and three separate garlic lines. They
    are distinct recipe lines but one trip to the store.
    """
    merged: dict[str, Buy] = {}
    for buy in buys:
        key = normalize_query(buy.item)
        if not key:
            continue
        if key in merged:
            keep = merged[key]
            if buy.source not in keep.source:
                keep.source = f"{keep.source}+{buy.source}"
            continue
        merged[key] = buy
    return list(merged.values())


def load_shopping(path: str | Path) -> list[Buy]:
    data = json.loads(Path(path).read_text())
    rows = [_row(raw, "plan") for raw in data.get("items", [])]
    return dedupe([b for b in rows if _is_buyable(b.item, b.aisle)])


def load_extras(path: str | Path, on: date | None = None) -> list[Buy]:
    data = json.loads(Path(path).read_text())
    today = on or date.today()
    out = [Buy(item=i["name"], buy=i.get("qty", ""), aisle=i["aisle"], source="extras")
           for i in data.get("fixed", [])]
    out += [Buy(item=f, buy="1", aisle="Fruit", source="extras")
            for f in data.get("fixed_fruit", [])]
    rotating = data.get("rotating_fruit", [])
    if rotating:
        out.append(Buy(item=rotating[today.isocalendar().week % len(rotating)],
                       buy="1", aisle="Fruit", source="extras"))
    if today.isocalendar().week % 2 == 0:
        out += [Buy(item=c, buy="1", aisle="Candy", source="extras")
                for c in data.get("chocolate_every_other_week", [])]
    return out
