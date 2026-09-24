"""Optional local advisors: Laya for verdicts, Jev for ranking.

Neither one speeds up the cart path. That path is limited by Walmart's request
rate, not by thinking, so no amount of local inference changes it. What they
remove is the API key -- both run locally, so an average user does not need a
cloud account to get a good match. That is the real unlock.

Measured on this project's own worst case, the line `dill sprigs`:

    jev_rank("fresh dill herb, a bunch, for garnish", [three candidates])
      Fresh Dill, 0.75 oz Clamshell                    3.74
      Dill Pickle Flavored Potato Chips                0.70
      OH SNAP! Dilly Bites Dill Pickle Snack Pack      0.69

Token overlap scored the snack pack 1.00, the highest score the system can give.
Jev put it last. 438ms, $0.000025, advisory only.

    laya_decide("tool_risk", {action: "add_to_cart", credentials_involved: True})
      verdict "ask_human"  (p=0.841)

Which is exactly what the agent should do with a live cart, and it arrives at
that answer without a rule for it.

Both are wired through MCP, so the transport is the same one walmart.py already
uses. With nothing configured the app runs on the built-in scorer alone, which
is why every function here has a null implementation and every call site can
take None.
"""
from __future__ import annotations

import json
import os
import shlex
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ENV_VAR = "MEAL_TO_CART_COUNSEL_CMD"


@dataclass
class Ranked:
    item_id: str
    score: float
    confidence: float = 0.0


@dataclass
class Risk:
    verdict: str
    reason: str = ""
    confidence: float = 0.0
    raw: dict = field(default_factory=dict)


def parse_rank(payload: str | dict) -> list[Ranked] | None:
    """Pull the ranking out of a Jev response, or None if it is not usable."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    content = data.get("content")
    if isinstance(content, list) and content:
        text = content[0].get("text", "")
        try:
            data = json.loads(text)
        except ValueError:
            return None
    ranking = data.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        return None
    out = []
    for row in ranking:
        try:
            out.append(Ranked(item_id=str(row["id"]), score=float(row["score"]),
                              confidence=float(row.get("confidence") or 0.0)))
        except (KeyError, TypeError, ValueError):
            return None
    return out


def parse_risk(payload: str | dict) -> Risk | None:
    """Pull the verdict out of a Laya response, or None if it is not usable."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    content = data.get("content")
    if isinstance(content, list) and content:
        text = content[0].get("text", "")
        try:
            data = json.loads(text)
        except ValueError:
            return None
    verdict = data.get("verdict")
    if not verdict:
        return None
    return Risk(verdict=str(verdict), reason=str(data.get("reason", "")),
                confidence=float(data.get("confidence") or 0.0), raw=data)


class Counsel(Protocol):
    available: bool

    async def rerank(self, query: str, candidates: list[dict]) -> list[Ranked] | None: ...
    async def risk(self, action: dict) -> Risk | None: ...


class NullCounsel:
    """The default. Keeps every call site free of 'is it configured' branches."""

    available = False

    async def rerank(self, query: str, candidates: list[dict]) -> list[Ranked] | None:
        return None

    async def risk(self, action: dict) -> Risk | None:
        return None


class MCPCounsel:
    """One stdio MCP server that exposes jev_rank and laya_decide.

    ```
    MEAL_TO_CART_COUNSEL_CMD="npx -y some-advisor-mcp" meal-to-cart --live
    ```
    """

    available = True

    def __init__(self, command: str) -> None:
        parts = shlex.split(command)
        if not parts:
            raise ValueError("empty counsel command")
        self.params = StdioServerParameters(command=parts[0], args=parts[1:], env=dict(os.environ))

    async def __aenter__(self) -> "MCPCounsel":
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(self.params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def _call(self, tool: str, args: dict) -> Any:
        result = await self.session.call_tool(tool, args)
        text = "\n".join(getattr(c, "text", "") for c in getattr(result, "content", []))
        try:
            return json.loads(text)
        except ValueError:
            return {"content": [{"text": text}]}

    async def rerank(self, query: str, candidates: list[dict]) -> list[Ranked] | None:
        items = [{"id": str(c.get("item_id")), "text": str(c.get("title", ""))}
                 for c in candidates if c.get("item_id")]
        if len(items) < 2:
            return None
        try:
            return parse_rank(await self._call("jev_rank", {"query": query, "items": items}))
        except Exception:  # noqa: BLE001 - an advisor must never break the run
            return None

    async def risk(self, action: dict) -> Risk | None:
        try:
            return parse_risk(await self._call("laya_decide",
                                               {"decision_id": "tool_risk", "state": action}))
        except Exception:  # noqa: BLE001
            return None


def from_env() -> Counsel:
    command = os.environ.get(ENV_VAR, "").strip()
    return MCPCounsel(command) if command else NullCounsel()


def apply_ranking(candidates: list[dict], ranked: list[Ranked]) -> list[dict]:
    """Reorder candidates best-first, keeping anything Jev did not score."""
    by_id = {str(c.get("item_id")): c for c in candidates}
    ordered = [by_id[r.item_id] for r in ranked if r.item_id in by_id]
    seen = {id(c) for c in ordered}
    return ordered + [c for c in candidates if id(c) not in seen]
