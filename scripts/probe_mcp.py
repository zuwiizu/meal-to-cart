"""Prove the Walmart MCP server runs and exposes what the agent needs.

    PYTHONPATH=src ./.venv/bin/python scripts/probe_mcp.py

Setup lives in scripts/setup_mcp.sh; the environment overrides that make the
server work under the file sandbox live in src/meal_to_cart/walmart.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from meal_to_cart.walmart import WalmartMCP  # noqa: E402

REQUIRED = ("status", "search", "add_to_cart", "view_cart")
PROBE_QUERY = "crumbled feta cheese"


async def probe() -> dict:
    async with WalmartMCP() as wm:
        tools = sorted(t.name for t in (await wm.session.list_tools()).tools)
        shape: dict[str, object] = {"status": await wm.status()}
        try:
            found = await wm.search(PROBE_QUERY, limit=3)
            shape["search"] = {"count": len(found), "first": found[0] if found else None}
        except Exception as exc:  # noqa: BLE001 - a probe records, it never raises
            shape["search"] = f"ERROR: {type(exc).__name__}: {exc}"
        return {"tools": tools, "shape": shape}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = asyncio.run(probe())
    missing = [t for t in REQUIRED if t not in payload["tools"]]
    if args.json:
        print(json.dumps(payload, default=str))
    else:
        print("tools:", ", ".join(payload["tools"]))
        print("status:", payload["shape"]["status"])
        print("search:", json.dumps(payload["shape"]["search"], indent=2, default=str)[:800])
    if missing:
        print(f"MISSING: {missing}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
