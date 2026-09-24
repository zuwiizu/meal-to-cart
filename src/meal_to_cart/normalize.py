"""Turn recipe prose into something a store search bar can accept.

Every example in the tests is a real line from the pipeline's own output, not
an invented edge case. The list this had to survive:

    'tablespoon fresh chives'            -> 'chives'
    'juice of 2 large limes )'           -> 'limes'
    'to 1/2 cup onions'                  -> 'onions'
    'lbs flank or skirt steak'           -> 'skirt steak'
    'pound chicken breast cut in half'   -> 'chicken breast'
    '(15oz tomato sauce)'                -> 'tomato sauce'
    '1% buttermilk'                      -> 'buttermilk'
    'teaspoon cinnamon, ground'          -> 'cinnamon'
    'medium garlic cloves'               -> 'garlic'
"""
from __future__ import annotations

import re

UNITS = {
    "teaspoon", "teaspoons", "tsp", "tablespoon", "tablespoons", "tbsp",
    "cup", "cups", "oz", "ounce", "ounces", "pound", "pounds", "lb", "lbs",
    "gram", "grams", "g", "kg", "ml", "l", "clove", "cloves", "head", "heads",
    "bunch", "bunches", "slice", "slices", "can", "cans", "package", "packages",
    "pkg", "pinch", "dash", "sprig", "sprigs", "stalk", "stalks", "fl", "qt",
}

# Words that carry no product meaning at the front of a line.
LEADING_NOISE = {
    "to", "about", "plus", "divided", "optional", "more", "as", "of", "or",
    "and", "each", "fresh", "large", "medium", "small", "ripe", "baby", "whole",
    "lean", "boneless", "skinless",
}

# 'garlic cloves' and '1 head of garlic' are the same purchase.
TRAILING_NOISE = {"cloves", "clove", "sprigs", "sprig", "leaves", "bulb", "bulbs"}

# Trailing prep instructions that no store search bar understands.
PREP_TAIL = re.compile(
    r"[, ]+\b(cut in half|cut into [a-z ]+|chopped|diced|minced|peeled|trimmed|"
    r"halved|quartered|rinsed|drained|ground|grated|shredded|thinly sliced)\b\.?$",
    re.I,
)

QUANTITY = re.compile(r"^[\d\s./¼½¾%\-]+$")
_OR_SPLIT = re.compile(r"\s+or\s+", re.I)
_STRAY = re.compile(r"[)\]}]+")
_PARENS_INNER = re.compile(r"^\((.*)\)$")
_PARENS = re.compile(r"\(.*?\)")
_JUICE_OF = re.compile(r"^juice of\s+", re.I)
# '(15oz tomato sauce)' welds the quantity to the unit.
_GLUED_QTY = re.compile(r"^\d+(?:\.\d+)?\s*(oz|lb|lbs|g|kg|ml|l|cups?|tsp|tbsp)\b\s*", re.I)
_WS = re.compile(r"\s+")

# The non-products: things a recipe needs but a store does not sell you.
FILLER = {
    "water", "boiling water", "hot water", "cold water", "warm water",
    "ice water", "tap water",
}

_LIQUID_UNITS = {"cup", "cups", "ml", "l", "liter", "litre"}


def _strip_leading(text: str) -> str:
    words = text.split()
    while words and (words[0] in UNITS or words[0] in LEADING_NOISE
                     or QUANTITY.match(words[0])):
        words.pop(0)
    return " ".join(words).strip(" ,.-")


def _strip_trailing(text: str) -> str:
    words = text.split()
    while words and words[-1] in TRAILING_NOISE:
        words.pop()
    return " ".join(words)


def normalize_query(name: str) -> str:
    text = name.strip().lower()
    inner = _PARENS_INNER.match(text)
    if inner:
        text = inner.group(1)
    text = _PARENS.sub(" ", text)
    text = _STRAY.sub("", text)
    text = _JUICE_OF.sub("", text)
    text = _GLUED_QTY.sub("", text)
    text = _WS.sub(" ", text).strip(" ,.-")

    if _OR_SPLIT.search(text):
        parts = [p.strip() for p in _OR_SPLIT.split(text)]
        usable = [p for p in parts if _strip_leading(p) not in FILLER]
        pool = usable or parts
        text = max(pool, key=lambda p: (len(_strip_leading(p).split()), -pool.index(p)))

    text = _strip_leading(text)
    text = PREP_TAIL.sub("", text)
    text = _strip_trailing(text)
    return text.strip(" ,.-")


def is_filler(name: str) -> bool:
    return normalize_query(name) in FILLER


def pack_hint(qty: str) -> str | None:
    """Rough size class, used to penalise an obviously wrong pack size."""
    q = (qty or "").strip().lower()
    if not q or "as needed" in q or "to taste" in q:
        return None
    number = re.search(r"\d+(?:\.\d+)?", q)
    if not number:
        return None
    unit = None
    match = re.search(r"[a-z]+", q)
    if match and match.group() in _LIQUID_UNITS:
        unit = match.group()
    if unit and float(number.group()) <= 0.75:
        return "small"
    return "standard"
