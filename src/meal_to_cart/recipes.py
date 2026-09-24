"""Turn a saved recipe link into ingredient lines.

Most recipe sites already publish the recipe in machine-readable form: a
`schema.org/Recipe` block in a JSON-LD script tag. That is what search engines
read, and it is exactly what we want -- so the default path needs no model, no
API key and no HTML heuristics. It is a JSON parse.

Social video has no such block, so that path is different: yt-dlp for the
caption/transcript, then a model. Rather than hide an optional heavyweight
dependency behind a flag, the agent extracts those and imports them through
`--import-recipes`, which takes the same shape this module produces. One code
path, two ways in.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urlparse

LD_JSON = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S,
)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


@dataclass
class Recipe:
    url: str
    title: str
    ingredients: list[str] = field(default_factory=list)
    source: str = ""
    servings: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.title and self.ingredients)


def _looks_like_recipe(node: dict) -> bool:
    kind = node.get("@type") or node.get("type") or ""
    if isinstance(kind, list):
        return any(str(k).lower() == "recipe" for k in kind)
    return str(kind).lower() == "recipe"


def _walk(node, found: list) -> None:
    if isinstance(node, list):
        for child in node:
            _walk(child, found)
    elif isinstance(node, dict):
        if _looks_like_recipe(node):
            found.append(node)
        for key in ("@graph", "mainEntity", "mainEntityOfPage", "itemListElement"):
            if key in node:
                _walk(node[key], found)


def _as_lines(value) -> list[str]:
    """One ingredient per line.

    A list is already one item per ingredient, so its commas belong to the
    ingredient ("1 onion, diced") and must not split it. Only a raw string needs
    splitting, and only on newlines and semicolons.
    """
    if isinstance(value, str):
        parts = re.split(r"\r?\n|\s*[;•]\s*", value)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.extend(p.strip() for p in item.splitlines() if p.strip())
            else:
                out.extend(_as_lines(item))
        return out
    return []


def parse_recipe(html: str, url: str = "") -> Recipe | None:
    """The first schema.org/Recipe in the page, or None."""
    candidates: list[dict] = []
    for block in LD_JSON.findall(html or ""):
        text = unescape(block).strip()
        try:
            _walk(json.loads(text), candidates)
        except ValueError:
            continue
    if not candidates:
        return None
    node = max(candidates, key=lambda n: len(_as_lines(n.get("recipeIngredient")
                                                       or n.get("ingredients"))))
    title = node.get("name") or ""
    if isinstance(title, list):
        title = title[0] if title else ""
    servings = node.get("recipeYield") or node.get("yield") or ""
    if isinstance(servings, list):
        servings = servings[0] if servings else ""
    return Recipe(
        url=url,
        title=unescape(str(title)).strip(),
        ingredients=_as_lines(node.get("recipeIngredient") or node.get("ingredients")),
        source=urlparse(url).netloc if url else "",
        servings=str(servings).strip(),
    )


def title_from_html(html: str) -> str:
    match = TITLE.search(html or "")
    return unescape(match.group(1)).strip() if match else ""


def fetch(url: str, timeout: float = 20.0) -> str:
    """Fetch a page. The only network call in this module."""
    import urllib.request

    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def from_url(url: str) -> Recipe | None:
    html = fetch(url)
    recipe = parse_recipe(html, url)
    if recipe is None:
        fallback = title_from_html(html)
        return Recipe(url=url, title=fallback, source=urlparse(url).netloc) if fallback else None
    return recipe


def load_import(path: str) -> list[Recipe]:
    """Read the shape produced for links that have no JSON-LD (social video)."""
    data = json.loads(open(path).read())
    rows = data if isinstance(data, list) else data.get("recipes", [])
    out: list[Recipe] = []
    for row in rows:
        out.append(Recipe(
            url=row.get("url", ""),
            title=row.get("title", ""),
            ingredients=_as_lines(row.get("ingredients") or row.get("recipeIngredient")),
            source=row.get("source", ""),
            servings=str(row.get("servings", "")),
        ))
    return [r for r in out if r.ok]
