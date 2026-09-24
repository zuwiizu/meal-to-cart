"""Persistent local state. SQLite from the standard library, one file.

Nothing here touches the network, and the file is gitignored: it holds what a
particular household already owns, which is nobody else's business.

Three things persist:
  * pantry    -- which staples you said you already have, so it asks once, not weekly
  * recipes   -- the links you saved, and what was extracted from them
  * runs      -- what each week's plan proposed, and what you approved
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pantry (
    item       TEXT PRIMARY KEY,
    status     TEXT NOT NULL CHECK (status IN ('have', 'need')),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipes (
    url        TEXT PRIMARY KEY,
    title      TEXT,
    source     TEXT,
    ingredients TEXT NOT NULL DEFAULT '[]',
    added_at   TEXT NOT NULL,
    verified   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    week       TEXT,
    summary    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS run_items (
    run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    query      TEXT NOT NULL,
    action     TEXT NOT NULL,
    item_id    TEXT,
    title      TEXT,
    confidence REAL,
    PRIMARY KEY (run_id, query)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- pantry ------------------------------------------------------------
    def set_pantry(self, item: str, status: str) -> None:
        assert status in ("have", "need"), status
        self.conn.execute(
            "INSERT INTO pantry (item, status, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(item) DO UPDATE SET status=excluded.status, "
            "updated_at=excluded.updated_at",
            (item.strip().lower(), status, _now()),
        )
        self.conn.commit()

    def pantry(self, status: str | None = None) -> dict[str, str]:
        sql = "SELECT item, status FROM pantry"
        args: tuple = ()
        if status:
            sql += " WHERE status = ?"
            args = (status,)
        return {row["item"]: row["status"] for row in self.conn.execute(sql, args)}

    def forget_pantry(self, item: str) -> None:
        self.conn.execute("DELETE FROM pantry WHERE item = ?", (item.strip().lower(),))
        self.conn.commit()

    # -- recipes -----------------------------------------------------------
    def add_recipe(self, url: str, title: str, source: str,
                   ingredients: list[str], verified: bool = False) -> None:
        self.conn.execute(
            "INSERT INTO recipes (url, title, source, ingredients, added_at, verified) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, "
            "ingredients=excluded.ingredients, verified=excluded.verified",
            (url.strip(), title, source, json.dumps(ingredients), _now(), int(verified)),
        )
        self.conn.commit()

    def recipes(self) -> list[dict]:
        return [
            {"url": r["url"], "title": r["title"], "source": r["source"],
             "ingredients": json.loads(r["ingredients"]), "verified": bool(r["verified"]),
             "added_at": r["added_at"]}
            for r in self.conn.execute("SELECT * FROM recipes ORDER BY added_at DESC")
        ]

    def recipe_ingredients(self) -> list[str]:
        seen: list[str] = []
        for recipe in self.recipes():
            for ingredient in recipe["ingredients"]:
                if ingredient not in seen:
                    seen.append(ingredient)
        return seen

    # -- runs --------------------------------------------------------------
    def record_run(self, week: str, summary: dict, items: list[dict]) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, week, summary) VALUES (?, ?, ?)",
            (_now(), week, json.dumps(summary)),
        )
        run_id = int(cur.lastrowid or 0)
        self.conn.executemany(
            "INSERT OR REPLACE INTO run_items "
            "(run_id, query, action, item_id, title, confidence) VALUES (?, ?, ?, ?, ?, ?)",
            [(run_id, i.get("query", ""), i.get("action", ""), i.get("item_id"),
              i.get("title", ""), i.get("confidence")) for i in items],
        )
        self.conn.commit()
        return run_id

    def last_run(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        items = [dict(r) for r in self.conn.execute(
            "SELECT * FROM run_items WHERE run_id = ?", (row["id"],))]
        return {"id": row["id"], "week": row["week"],
                "summary": json.loads(row["summary"]), "items": items}
