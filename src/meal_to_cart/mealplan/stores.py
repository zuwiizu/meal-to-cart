"""A profile's shops, read by key.

The keys are the contract (the demo's own stores.json says so): a stop is
looked up by key, never by display name, because names are for people and
keys are for wiring. A profile with no store for the retailer simply has no
stop -- and a cart link carries a store id from exactly one place, this
file's reader, so a store can never be half-guessed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stop:
    key: str
    label: str
    role: str = ""
    store_id: str = ""


def build_store_plan(stores) -> list[Stop]:
    """The profile's stops, in file order, keyed the way build_week reads
    them. Accepts the stores path or an already-loaded row list."""
    if isinstance(stores, (str, Path)):
        path = Path(stores)
        if not path.is_file():
            return []
        data = json.loads(path.read_text())
    else:
        data = {"stores": stores or []}
    rows = data.get("stores") if isinstance(data, dict) else data
    out: list[Stop] = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("key"):
            continue
        out.append(Stop(
            key=str(row["key"]),
            label=str(row.get("name") or row["key"]),
            role=str(row.get("role") or ""),
            store_id=str(row.get("storeId") or ""),
        ))
    return out
