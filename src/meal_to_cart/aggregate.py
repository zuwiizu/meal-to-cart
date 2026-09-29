"""Aisle guesswork and amount reading -- the two deterministic conveniences
the pipeline needs before a search can happen.

Neither calls a model and neither calls the network: an aisle is a word
table and an amount is a number pulled out of the text the recipe wrote.
When this file guesses, it guesses the way a person reads a list -- and when
it cannot read a number, it says so (known=False) rather than returning
zero, because zero is an amount somebody stated and known=False is the
absence that has to survive all the way to the seam.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_UNICODE_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
_FRACTION = re.compile(r"(\d+)\s*/\s*(\d+)")
_NUMBER = re.compile(r"(\d+(?:\.\d+)?|\d*\.\d+)")


@dataclass(frozen=True)
class Amount:
    quantity: float | None
    known: bool


def parse_amount(text: str) -> Amount:
    """The first number in the text, or known=False.

    '2 teaspoon' -> 2.0, '0.5 teaspoon' -> 0.5, '1/2 cup' -> 0.5, '6' -> 6.0;
    'as needed', 'to taste' and '' are all known=False -- an absence, not a
    zero, and the difference is the whole refusal story downstream.
    """
    text = str(text or "")
    for char, value in _UNICODE_FRACTIONS.items():
        if char in text:
            return Amount(value, True)
    match = _FRACTION.search(text)
    if match:
        denominator = float(match.group(2))
        if denominator:
            return Amount(float(match.group(1)) / denominator, True)
    match = _NUMBER.search(text)
    if match:
        return Amount(float(match.group(1)), True)
    return Amount(None, False)


# --- aisles ---------------------------------------------------------------
#
# A word table, checked in order. It exists so a line says where in the shop
# it lives; it is cosmetic and deliberately not clever.

_PHRASES = (
    ("bell pepper", "produce"), ("bell peppers", "produce"),
    ("black pepper", "pantry"), ("white pepper", "pantry"),
    ("cayenne pepper", "pantry"), ("green bean", "produce"),
    ("green onion", "produce"), ("red onion", "produce"),
    ("sweet potato", "produce"),
)
_DRIED_FORMS = {"powder", "dried", "seasoning", "spice", "spices"}
_PRODUCE = {
    "onion", "onions", "garlic", "tomato", "tomatoes", "potato", "potatoes",
    "lemon", "lemons", "lime", "limes", "orange", "orange", "apple", "apple",
    "banana", "bananas", "avocado", "avocados", "pepper", "peppers",
    "jalapeno", "broccoli", "carrot", "carrots", "celery", "cucumber",
    "zucchini", "spinach", "lettuce", "kale", "cabbage", "mushroom",
    "mushrooms", "ginger", "scallion", "scallions", "shallot", "shallots",
    "parsley", "cilantro", "basil", "mint", "dill", "thyme", "rosemary",
    "chives", "sage", "berry", "berries", "strawberry", "blueberry",
    "eggplant", "squash", "asparagus", "cauliflower", "corn", "peas",
    "herb", "herbs",
}
_MEAT = {
    "chicken", "beef", "pork", "turkey", "salmon", "shrimp", "fish",
    "steak", "bacon", "sausage", "thigh", "thighs", "breast", "lamb",
    "cod", "tuna", "prawn", "prawns", "ground", "mince",
}
_DAIRY = {
    "milk", "butter", "cheese", "yogurt", "cream", "egg", "eggs",
    "mozzarella", "parmesan", "cheddar", "feta", "ricotta",
}
_BAKERY = {
    "bread", "tortilla", "tortillas", "bun", "buns", "roll", "rolls",
    "pita", "bagel", "bagels", "baguette", "naan",
}
_BEVERAGES = {"juice", "soda", "seltzer", "coffee", "tea", "wine", "beer"}


def aisle_for(item: str) -> str:
    """The aisle this line most likely lives down."""
    text = str(item or "").lower()
    for phrase, aisle in _PHRASES:
        if phrase in text:
            return aisle
    words = set(re.findall(r"[a-z]+", text))
    if words & _DRIED_FORMS:
        return "pantry"
    if "frozen" in words:
        return "frozen"
    if words & _PRODUCE:
        return "produce"
    if words & _MEAT:
        return "meat & seafood"
    if words & _DAIRY:
        return "dairy & eggs"
    if words & _BAKERY:
        return "bakery"
    if words & _BEVERAGES:
        return "beverages"
    return "pantry"
