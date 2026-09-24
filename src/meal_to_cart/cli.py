"""meal-to-cart: weekly dinner plan -> reviewed Walmart cart.

    python -m meal_to_cart.cli --dry-run          # no network, no credentials
    python -m meal_to_cart.cli --live --limit 8   # real searches, real cart

The run always stops before payment. There is no code path that pays.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from .cart import apply, build_plan, render
from .load import load_extras, load_shopping
from .match import score
from .models import MatchResult
from .normalize import normalize_query
from .walmart import WalmartMCP, load_cache, reset_session

RUNS = Path(__file__).resolve().parents[2] / "site" / "data"


def collect(shopping: str, extras: str, limit: int | None) -> list:
    buys = load_shopping(shopping) + load_extras(extras, on=date.today())
    return buys[:limit] if limit else buys


def dump(results: list[MatchResult], summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "summary": summary,
        "results": [
            {
                "action": r.action,
                "confidence": r.confidence,
                "item_id": r.item_id,
                "title": r.title,
                "price": r.price,
                "price_text": r.price_text,
                "reason": r.reason,
                "query": r.query,
                "buy": {
                    "item": r.buy.item,
                    "buy": r.buy.buy,
                    "aisle": r.buy.aisle,
                    "meals": r.buy.meals,
                    "source": r.buy.source,
                },
            }
            for r in results
        ],
    }, indent=2))


async def run(args) -> int:
    buys = collect(args.shopping, args.extras, args.limit)
    print(f"{len(buys)} lines to consider "
          f"({sum(1 for b in buys if b.source == 'extras')} of them extras)")

    if args.dry_run:
        results = [score(b, normalize_query(b.item), []) for b in buys]
        print(render(results))
        print(f"\n[dry-run] {len(results)} lines staged. No network, no cart writes.")
        dump(results, {"would_add": 0, "added": 0, "denied": 0,
                       "skipped_flagged": len(results)}, RUNS / "dry-run.json")
        return 0

    if args.replay:
        cache = load_cache()
        results = []
        for buy in buys:
            query = normalize_query(buy.item)
            candidates = cache.get(query)
            if candidates is None:
                results.append(MatchResult(buy=buy, query=query, action="flag",
                                           reason="not searched yet"))
            else:
                results.append(score(buy, query, candidates))
        print(render(results))
        known = [r for r in results if r.item_id is not None]
        print(f"\n[replay] {len(known)}/{len(results)} lines matched from cache, "
              f"no network used")
        dump(results, {"would_add": len(known), "added": 0, "denied": 0,
                       "skipped_flagged": len(results) - len(known),
                       "replayed": True},
             RUNS / "demo-run.json")
        return 0

    if reset_session():
        print("cleared a stale session cookie jar")

    async with WalmartMCP(use_cache=not args.no_cache) as wm:
        print("status:", (await wm.status()).splitlines()[0])

        def progress(index: int, total: int, result: MatchResult) -> None:
            print(f"  [{index:>2}/{total}] {result.action:4} "
                  f"{result.confidence:.2f} {normalize_query(result.buy.item)}")

        results = await build_plan(buys, wm, on_progress=progress, pause=args.pause)
        if wm.hits:
            print(f"  ({wm.hits} of {len(buys)} answered from cache)")
        print()
        print(render(results))
        flagged = [r for r in results if r.action != "add"]
        print(f"\n{len(results) - len(flagged)} matched, {len(flagged)} need your call")

        def approve(result: MatchResult) -> bool:
            if args.yes:
                return True
            try:
                answer = input(f"add {result.title} "
                               f"({result.price_text or 'price ?'})? [Y/n] ")
            except EOFError:
                # Non-interactive run: silence is not consent.
                return False
            return answer.strip().lower() in ("", "y", "yes")

        summary = await apply(results, wm, approve)
        print(json.dumps(summary, indent=2))
        cart = await wm.view_cart()
        print("cart:", cart[:500])
        dump(results, summary, RUNS / "live-run.json")
        print("\nSTOPPING BEFORE CHECKOUT. Payment is yours to make.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meal-to-cart")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--shopping", default=str(root / "data/sample/shopping.sample.json"))
    parser.add_argument("--extras", default=str(root / "data/extras.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pause", type=float, default=25.0,
                        help="seconds between searches; Walmart blocks on rate")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true",
                        help="auto-approve matches (still never checks out)")
    parser.add_argument("--replay", action="store_true",
                        help="rebuild the full plan from cached searches, offline")
    parser.add_argument("--no-cache", action="store_true",
                        help="ignore cached searches and hit the network")
    args = parser.parse_args(argv)
    if not args.dry_run:
        args.live = True
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
