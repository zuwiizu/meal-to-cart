"""The shop this engine fills, and the link that fills one.

One retailer so far, described once here so nothing downstream spells its
URL, its id field or its search query by hand. The cart link is the
first-party add-to-cart URL the store itself uses; it carries the store id
because the store decides what is on the shelf, and it opens a cart a HUMAN
reviews -- this engine stops before payment, by design.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

BASE_URL = "https://www.walmart.com"


@dataclass(frozen=True)
class Retailer:
    key: str          # the name a profile's stores slot is keyed by
    label: str        # what a person reads
    id_field: str     # what the store calls a product id
    base: str = BASE_URL


WALMART = Retailer(key="walmart", label="Walmart", id_field="usItemId")


class CartLine(NamedTuple):
    """One line of a cart link: a product id and a count."""
    item_id: str
    quantity: int


def _as_line(entry) -> CartLine:
    if isinstance(entry, CartLine):
        return entry
    if hasattr(entry, "item_id") and hasattr(entry, "quantity"):
        return CartLine(str(entry.item_id), int(entry.quantity))
    if isinstance(entry, (tuple, list)) and len(entry) == 2:
        return CartLine(str(entry[0]), int(entry[1]))
    text = str(entry)
    item_id, _, qty = text.rpartition("_")
    return CartLine(item_id or text, int(qty) if qty.isdigit() else 1)


def render_cart_link(lines, store_id: str) -> str:
    """The cart link, then the human half, as one string.

    Refuses an empty cart and refuses a missing store id, both by design: an
    empty link is the "cart with holes" this project exists to refuse, and a
    guessed store id would fill a cart at a shop the visitor does not use.
    The URL is the first line; callers that need it alone split on the blank
    line below it (the app puts it in an href, where a newline would be
    stripped and the summary would forge a different cart).
    """
    lines = [_as_line(line) for line in lines]
    if not lines:
        raise ValueError(
            "refusing to render an empty cart: a link with no lines in it is "
            "the cart-with-holes this tool exists to refuse")
    store_id = str(store_id or "").strip()
    if not store_id:
        raise ValueError(
            "refusing to render without a store id: the store decides what "
            "is on the shelf, and a guessed id fills a cart at the wrong shop")
    items = ",".join(f"{line.item_id}_{line.quantity}" for line in lines)
    url = f"{BASE_URL}/sc/cart/addToCart?items={items}&storeId={store_id}"
    summary = "\n".join([
        f"{len(lines)} line(s) matched at {WALMART.label}, store {store_id}.",
        *(f"- {line.quantity} x {WALMART.id_field} {line.item_id}"
          for line in lines),
        "Open the link to review the cart; check out yourself. This tool "
        "stops before payment.",
    ])
    return f"{url}\n\n{summary}"
