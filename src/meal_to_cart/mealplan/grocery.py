"""A week's nights, merged into one line per purchase.

The merge key is canonical(item) -- the same "is this the same thing" key
the pantry uses -- because two nights should cost ONE bunch of parsley, not
two lines that each look small. Amounts are summed only when both numbers
were stated: an absence stays an absence (None), because zero is an amount
and a recipe that said nothing did not say zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..normalize import canonical


@dataclass
class Line:
    """One purchase's worth of a week: summed amount, nights it came from."""
    item: str
    qty: float | None = None
    unit: str = ""
    need: str = ""
    nights: list[str] = field(default_factory=list)


def _need(qty: float | None, unit: str) -> str:
    if qty is None:
        return "some"
    text = f"{qty:g} {unit}".strip()
    return text or "some"


def aggregate(days: list[dict]) -> list[Line]:
    """One line per distinct item, with the week's own amounts and nights."""
    merged: dict[str, Line] = {}
    for day in days or []:
        name = str(day.get("day") or "")
        for recipe in day.get("recipes") or []:
            for ingredient in recipe.get("ingredients") or []:
                item = str(ingredient.get("item") or "").strip()
                if not item:
                    continue
                key = canonical(item) or item.lower()
                qty = ingredient.get("qty")
                unit = str(ingredient.get("unit") or "").strip()
                if key not in merged:
                    merged[key] = Line(item=item)
                line = merged[key]
                if isinstance(qty, (int, float)):
                    line.qty = (float(qty) if line.qty is None
                                else line.qty + float(qty))
                if unit and not line.unit:
                    line.unit = unit
                if name and name not in line.nights:
                    line.nights.append(name)
    lines = list(merged.values())
    for line in lines:
        line.need = _need(line.qty, line.unit)
    return lines
