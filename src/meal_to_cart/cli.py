"""The household's own run: links in, week out, no browser anywhere.

    python3 -m meal_to_cart.cli --link https://... [--link https://...]
                                 [--profile demo] [--json out.json]

The same pipeline the app drives -- importer, planner, grocery, shopping,
the seam, the gateway -- assembled here so the household can run it from a
terminal and a reviewer can watch every step without a browser. It prints
the week, the list, the refusals and the cart link, and it never checks
anything out.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import gateway, household, profile
from .aggregate import parse_amount
from .cart import build_plan
from .importer import import_recipe
from .mealplan.grocery import aggregate
from .mealplan.planner import plan_week
from .mealplan.rules import Ruleset
from .mealplan.shopping import optimize, why_dropped
from .mealplan.stores import build_store_plan
from .resolve import NoProduct, Product, Unknown, resolve
from .walmart import WalmartHTTP


def _values(profile_name: str) -> dict:
    path = profile.values_path(profile_name)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError:
        return {}


def _qty(amount: str):
    parsed = parse_amount(amount)
    return parsed.quantity if parsed.known else None


def run(profile_name: str, links: list[str], matcher=None) -> dict:
    """One week, assembled exactly the way the app assembles it."""
    values = _values(profile_name)
    dinners = int((values.get("plan") or {}).get("dinners") or 5)

    recipes, unresolved = [], []
    for raw in (import_recipe(url) for url in links):
        if not raw.ingredients:
            unresolved.append({"line": raw.source,
                               "reason": raw.note or "no ingredient list"})
            continue
        recipes.append({
            "source": raw.source, "title": raw.title,
            "creator": raw.creator, "confidence": raw.confidence,
            "ingredients": [
                {"item": ing.item, "qty": _qty(ing.amount), "unit": ing.unit}
                for ing in raw.ingredients],
        })

    try:
        paths = profile.paths(profile_name)
    except profile.UnknownProfile:
        paths = {}
    ruleset = (Ruleset.load(paths["rules"]) if "rules" in paths
               else Ruleset([]))
    plan = (plan_week(recipes, ruleset, household.preferences(profile_name),
                      days=dinners)
            if recipes else
            {"days": [], "notes": [], "rejected": [], "review": []})

    lines = aggregate(plan["days"])
    buys, dropped = optimize(plan["days"], lines)
    for item in dropped:
        unresolved.append({"line": item, "reason": why_dropped(item)})

    results = asyncio.run(build_plan(buys, matcher or WalmartHTTP()))
    by_line = {id(r.buy): r for r in results}

    def _lookup(line, retailer, wanted):
        found = by_line.get(id(line))
        if found is None:
            return NoProduct("the line was never searched: it carries no query")
        if found.action == "add" and found.item_id:
            return Product(item_id=found.item_id, quantity=1,
                           title=found.title, price=found.price,
                           why=found.reason)
        return NoProduct(found.reason or
                         "no product at the store matched this line")

    resolved: list = []
    for line in buys:
        answer = resolve(line, lookup=_lookup)
        if isinstance(answer, Unknown):
            unresolved.append({"line": answer.item, "reason": answer.reason})
        else:
            resolved.append(answer)

    stops = build_store_plan(paths["stores"]) if "stores" in paths else []
    store_id = next((s.store_id for s in stops
                     if s.key == gateway.WALMART.key and s.store_id), None)
    cart_link = None
    if resolved and not unresolved and store_id:
        rendered = gateway.render_cart_link(
            [answer.cart_line() for answer in resolved], store_id)
        cart_link = rendered.partition("\n\n")[0]
    return {"plan": plan, "shopping": [vars(buy) for buy in buys],
            "resolved": len(resolved), "unresolved": unresolved,
            "cart_link": cart_link, "store": store_id}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="meal-to-cart",
        description="Turn recipe links into a week and a reviewed cart link.")
    parser.add_argument("--profile", default="demo",
                        help="which profile's values/rules/stores to use")
    parser.add_argument("--link", action="append", default=[],
                        help="a recipe link (repeat for more nights)")
    parser.add_argument("--json", dest="json_path", default="",
                        help="write the whole run to this file")
    args = parser.parse_args(argv)
    if not args.link:
        parser.error("at least one --link is required: the week is built "
                     "from the recipes you bring")

    out = run(args.profile, args.link)
    print("The week")
    for day in out["plan"]["days"]:
        names = ", ".join(recipe.get("title") or recipe.get("source") or "?"
                          for recipe in day.get("recipes") or [])
        print(f"  {day['day']:<10} {names or '-- (bring another link)'}")
    for note in out["plan"]["notes"]:
        print(f"  note: {note}")

    print("\nThe list")
    for row in out["shopping"]:
        nights = ", ".join(row["meals"]) or "--"
        print(f"  {row['aisle']:<15} {row['item']:<24} "
              f"buy {row['buy']:<12} ({nights})")

    blocked = [row for row in out["unresolved"] if row["line"] in
               {r["item"] for r in out["shopping"]}]
    named = [row for row in out["unresolved"] if row not in blocked]
    if blocked:
        print("\nOn the list but not addable (named, not hidden)")
        for row in blocked:
            print(f"  {row['line']}: {row['reason']}")
    if named:
        print("\nNot on the list (named, not hidden)")
        for row in named:
            print(f"  {row['line']}: {row['reason']}")

    print()
    if out["cart_link"]:
        print("Cart link (yours to review; nothing is ordered):")
        print(out["cart_link"])
    elif out["unresolved"]:
        print("No link was emitted: a cart with holes in it is worse than "
              "none.")
        print("The reasons above are the holes.")
    elif not out["store"]:
        print("No link was emitted: this profile names no Walmart store "
              "id, and the link needs one.")
    else:
        print("No link was emitted: there was nothing to add.")
    if args.json_path:
        with open(args.json_path, "w") as handle:
            json.dump(out, handle, indent=2)
        print(f"\nSaved {args.json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
