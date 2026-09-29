"""The seam: a planned line becomes a product, or a named refusal.

This module NEVER searches. The search is handed in (lookup), exactly as the
importer takes its fetch, for one reason: the moment the seam can do I/O,
the engine has two search paths that can disagree, and this seam is supposed
to be the single place the two halves of the pipeline meet. resolve() with
no lookup raises rather than inventing an answer.

A line with no amount is refused HERE, before any lookup runs. The recipe
did not state how many, the importer did not invent one, and this seam will
not invent one either -- "does not state one usable amount" is the refusal
the whole project is built around: better a named hole than a cart with one.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import gateway
from .aggregate import parse_amount


@dataclass(frozen=True)
class Resolved:
    """A line and the product behind it."""
    line: object
    retailer: object
    wanted: frozenset
    item_id: str
    quantity: int
    title: str = ""
    price: float | None = None

    def cart_line(self) -> gateway.CartLine:
        return gateway.CartLine(str(self.item_id), int(self.quantity))


@dataclass(frozen=True)
class Unknown:
    """A line and the reason it is not a product. The reason is never blank."""
    line: object
    retailer: object
    item: str
    reason: str


@dataclass(frozen=True)
class Product:
    """The lookup's success answer.

    quantity has NO default, and neither does Resolved's: a count is a
    number the engine states, never one this file guessed.
    """
    item_id: str
    quantity: int
    title: str = ""
    price: float | None = None
    why: str = ""


@dataclass(frozen=True)
class NoProduct:
    """The lookup's refusal: why this line is not a product at this retailer."""
    reason: str


# The type a caller may annotate with; both members are the whole set, and a
# review should never need to ask what else resolve() can return.
Resolution = Resolved | Unknown


def resolve(line, lookup=None) -> Resolution:
    """One line's answer: a Resolved or an Unknown, never neither.

    Refuses unsized lines first (the seam's own rule, before any lookup),
    then asks the injected lookup in this retailer's terms.
    """
    retailer = getattr(line, "retailer", None) or gateway.WALMART
    item = str(getattr(line, "item", "") or "")
    wanted = frozenset({item})
    amount = str(getattr(line, "buy", "") or "")
    if not parse_amount(amount).known:
        return Unknown(
            line, retailer, item,
            f"{item!r} does not state one usable amount to buy: the recipe "
            f"gave no number, and this seam will not invent one")
    if lookup is None:
        raise RuntimeError(
            "resolve() needs the product lookup handed in; the seam never "
            "searches on its own")
    answer = lookup(line, retailer, wanted)
    if isinstance(answer, NoProduct):
        return Unknown(line, retailer, item,
                       answer.reason or "no product at this retailer")
    return Resolved(
        line, retailer, wanted=wanted,
        item_id=str(answer.item_id), quantity=int(answer.quantity),
        title=answer.title, price=answer.price)
