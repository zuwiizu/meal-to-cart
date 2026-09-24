"""A tiny local HTTP surface so the published page can reach a real agent.

    python -m meal_to_cart.server --port 8787

The deployed page is static -- it cannot hold a Walmart session or run a
browser. This process does, on the machine that owns the login. Expose it for
a demo with:

    cloudflared tunnel --url http://127.0.0.1:8787
"""
from __future__ import annotations

import argparse
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .match import score
from .models import Buy
from .normalize import normalize_query
from .walmart import WalmartMCP

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "site" / "data"


def _match_one(query: str) -> dict:
    async def go() -> dict:
        async with WalmartMCP() as wm:
            candidates = await wm.search(query, limit=5)
            result = score(Buy(item=query), query, candidates)
            return {
                "action": result.action,
                "confidence": result.confidence,
                "item_id": result.item_id,
                "title": result.title,
                "price": result.price,
                "price_text": result.price_text,
                "query": query,
                "buy": {"item": query, "buy": "", "aisle": "Ad hoc", "source": "user"},
            }
    return asyncio.run(go())


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send({"ok": True})
        if parsed.path == "/runs/latest":
            latest = RUNS / "live-run.json"
            if not latest.exists():
                return self._send({"error": "no run recorded yet"}, 404)
            return self._send(json.loads(latest.read_text()))
        if parsed.path == "/match":
            query = (parse_qs(parsed.query).get("q") or [""])[0].strip()
            query = normalize_query(query)
            if not query:
                return self._send({"error": "empty query"}, 400)
            try:
                return self._send(_match_one(query))
            except Exception as exc:  # noqa: BLE001 - report, never crash the server
                return self._send({"error": f"{type(exc).__name__}: {exc}"}, 502)
        self._send({"error": "not found"}, 404)

    def log_message(self, *args) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="meal-to-cart-server")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    print(f"meal-to-cart agent on http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
