"""Lines to buys: the ones a store sells, and the two kinds it does not.

A line is DROPPED only when no cart could ever hold it -- and optimize()
has exactly two predicates for that, neither of which is a purchase:

  * is_non_ingredient(item): equipment (skewers, foil) and water. A
    shopping list that says this wastes a trip down an aisle.
  * _is_instruction(item): a sentence that fell out of the recipe as an
    ingredient ("preheat the oven to 400"). It came out of the recipe with
    no amount, because it was never an ingredient at all.

A line is NOT dropped for lacking an amount. An unsized line goes to the
seam, which refuses it in the visitor's own hearing ("does not state one
usable amount"). Dropping it here would hide the hole; the whole point is a
named hole instead of a short list that looks complete.

The one judgement call is a vague amount with an obvious buy: "a handful of
parsley" is not a number, but a bunch of parsley is a purchase, and the
aggregator is allowed to say so. "Some" stays refused.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..aggregate import aisle_for
from ..normalize import canonical, is_filler

# Amounts with no number that still name a purchase.
CONCRETE = {"handful": "1 bunch"}

# Equipment and water: things a recipe lists as ingredients and a store
# does not sell.
NON_INGREDIENT = {
    "skewers", "wooden skewers", "toothpicks", "foil", "aluminum foil",
    "parchment", "parchment paper", "plastic wrap", "cling wrap",
    "twine", "kitchen twine", "butcher twine", "string", "air fryer",
    "slow cooker", "dutch oven", "sheet pan", "grill", "grill pan",
    "skillet", "saucepan", "stockpot", "splatter screen", "thermometer",
    "meat thermometer", "ice",
}

# A sentence, not an ingredient: leads with a verb and runs long enough to
# be instructions. Kept separate from NON_INGREDIENT so the app's reader
# can say WHICH kind of line was dropped without guessing.
_INSTRUCTION_STARTS = {
    "preheat", "heat", "combine", "mix", "stir", "toss", "whisk",
    "transfer", "serve", "pour", "place", "add", "cook", "bake", "roast",
    "boil", "simmer", "drain", "rinse", "spray", "line", "wrap", "rest",
    "garnish", "sprinkle", "season", "divide", "cut", "slice", "chop",
    "remove", "set",
}

_REUSE = {
    "garlic": "extra cloves keep for weeks in a cool, dry spot",
    "parsley": "the other half of the bunch keeps a few days",
    "cilantro": "the other half of the bunch keeps a few days",
    "dill": "the other half of the bunch keeps a few days",
    "mint": "the other half of the bunch keeps a few days",
    "basil": "the other half of the bunch keeps a few days",
    "lemon": "extra lemons keep two weeks in the fridge",
    "lime": "extra limes keep a couple of weeks in the fridge",
}


@dataclass
class Buy:
    """One purchase, in the shape the site shows and the seam reads."""
    item: str
    buy: str = ""
    aisle: str = ""
    meals: list[str] = field(default_factory=list)
    need: str = ""
    spare: str = ""
    form: str = ""


def is_non_ingredient(item: str) -> bool:
    """True for a line no cart could hold: equipment, or water itself."""
    key = canonical(item)
    if not key:
        return True
    if key in {canonical(name) for name in NON_INGREDIENT}:
        return True
    return is_filler(item)


def _is_instruction(item: str) -> bool:
    words = re.findall(r"[a-z]+", str(item or "").lower())
    return bool(words) and words[0] in _INSTRUCTION_STARTS and len(words) >= 3


def _buy_text(line) -> str:
    """How much of it to buy, in the recipe's own words when it gave any."""
    if line.qty is not None:
        return f"{line.qty:g} {line.unit}".strip()
    unit = str(line.unit or "").strip().lower()
    return CONCRETE.get(unit, "as needed")


def _spare(line, buy_text: str) -> str:
    text = buy_text.lower()
    if not any(word in text for word in ("bunch", "head", "cloves", "sprigs")):
        return ""
    key = canonical(line.item)
    for word, note in _REUSE.items():
        if word in key:
            return note
    return ""


def optimize(days: list[dict], lines: list) -> tuple[list[Buy], list[str]]:
    """(buys, dropped): every line becomes a buy or a NAMED drop."""
    dropped: list[str] = []
    buys: list[Buy] = []
    for line in lines or []:
        item = str(getattr(line, "item", "") or "").strip()
        if not item:
            continue
        if is_non_ingredient(item) or _is_instruction(item):
            dropped.append(item)
            continue
        buy_text = _buy_text(line)
        buys.append(Buy(
            item=item,
            buy=buy_text,
            aisle=aisle_for(item),
            meals=list(getattr(line, "nights", []) or []),
            need=str(getattr(line, "need", "") or ""),
            spare=_spare(line, buy_text),
            form="",
        ))
    return buys, dropped


def why_dropped(item: str) -> str:
    """The dropped line's name and the reason, in the visitor's words.

    The engine's optimize() hands back the refused line's name and nothing
    else, so the case is re-read from the same predicate rather than
    guessed at.
    """
    if is_non_ingredient(item):
        return ("not food - a shopping list that says this wastes a trip "
                "down an aisle")
    return ("a cooking instruction rather than a purchase: it came out of "
            "the recipe with no amount")
