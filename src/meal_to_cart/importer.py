"""Read a recipe link into ingredient lines.

The default path is the page's own machine-readable publication: most
recipe sites embed a schema.org/Recipe block in a JSON-LD script tag -- the
same thing search engines read. That is a JSON parse: no model, no key, no
per-page tweaking, and no cost.

The fallback is the same reader on plain text. A page read as text (a saved
fixture, a pasted page) still has a title and an ingredient section, and
reading them is the same job -- which is why the engine's own tests can pin
this reader without a network, and why the live recording and the test
suite read their inputs through the same code.

The importer NEVER invents an amount: "salt, to taste" keeps its empty
amount here and the seam refuses it later, in the visitor's hearing. When a
page cannot be read at all, that truth comes back as a named note -- never
as an empty recipe that looks fine.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urlparse

UA = ("meal-to-cart/0.1 (personal recipe reader; one saved page per link, "
      "no crawling)")

LD_JSON = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S)
HTML_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
HTML_TAG = re.compile(r"<[^>]+>")
MD_TITLE = re.compile(r"^\s*(?:#\s*)?(?:Title|Recipe)\s*:\s*(.+)$", re.I | re.M)
MD_CREATOR = re.compile(r"^\s*(?:Creator|Author|Source)\s*:\s*(.+)$",
                        re.I | re.M)
ING_HEADING = re.compile(
    r"^#{1,6}\s*Ingredients\s*$|^Ingredients\s*:?\s*$", re.I | re.M)
BULLET = re.compile(
    r"^\s*(?:[-*•‣·]\s+|\d+[.)]\s+)(.*\S)\s*$")

_AMOUNT = re.compile(
    r"^((?:\d+\s+)?\d+\s*/\s*\d+|\d+(?:\.\d+)?|½|¼|¾|⅓|⅔|"
    r"one|two|three|four|five|six|seven|eight|nine|ten)\b\.?\s+(.*)$",
    re.I)
_A_HANDFUL = re.compile(r"^a\s+(handful|pinch)\s+of\s+(.+)$", re.I)

_UNICODE_AMOUNTS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
_WORD_AMOUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# Units a line may open with after its number.
_UNITS = {
    "teaspoon", "teaspoons", "tsp", "tablespoon", "tablespoons", "tbsp",
    "cup", "cups", "oz", "ounce", "ounces", "pound", "pounds", "lb", "lbs",
    "gram", "grams", "kg", "ml", "l", "clove", "cloves", "head", "heads",
    "bunch", "bunches", "slice", "slices", "can", "cans", "package",
    "packages", "pkg", "pinch", "dash", "sprig", "sprigs", "stalk",
    "stalks", "qt", "quart", "quarts", "pint", "pints", "gallon", "gallons",
    "liter", "liters", "stick", "sticks", "jar", "jars", "packet",
    "packets", "bottle", "bottles", "box", "boxes", "handful", "handfuls",
}
_UNIT_ALIASES = {
    "tsp": "teaspoon", "teaspoons": "teaspoon",
    "tbsp": "tablespoon", "tablespoons": "tablespoon",
    "oz": "ounce", "ounces": "ounce",
    "lb": "pound", "lbs": "pound", "pounds": "pound",
    "package": "package", "packages": "package", "pkg": "package",
    "pint": "pint", "pints": "pint", "quart": "quart", "quarts": "quart",
    "stalk": "stalk", "stalks": "stalk",
}
# Modifiers that lead a line and mean nothing to a store search.
_LEADING = {
    "fresh", "freshly", "dried", "large", "small", "medium", "ripe",
    "baby", "whole", "boneless", "skinless", "lean", "organic", "halved",
    "quartered", "peeled", "trimmed", "thawed", "chilled", "cold",
}
_PARENS = re.compile(r"\(.*?\)")


@dataclass
class Ingredient:
    """One parsed ingredient line."""
    item: str
    amount: str = ""
    unit: str = ""
    raw: str = ""


@dataclass
class ImportedRecipe:
    """One link's recipe, or the named reason there is none."""
    source: str = ""
    title: str = ""
    creator: str = ""
    confidence: float = 0.0
    note: str = ""
    ingredients: list[Ingredient] = field(default_factory=list)


def _num_text(value: float) -> str:
    return ("%g" % round(value, 3))


def _to_number(text: str) -> float | None:
    text = str(text or "").strip().lower()
    if text in _WORD_AMOUNTS:
        return float(_WORD_AMOUNTS[text])
    if text in _UNICODE_AMOUNTS:
        return _UNICODE_AMOUNTS[text]
    parts = text.split()
    if len(parts) == 2 and "/" in parts[1]:
        whole = _to_number(parts[0])
        rest = _to_number(parts[1])
        return None if whole is None or rest is None else whole + rest
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            return float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _unit_or_none(word: str) -> str | None:
    key = str(word or "").strip().strip(".").lower()
    if key in _UNITS:
        return _UNIT_ALIASES.get(key, key)
    return None


def _clean_item(text: str) -> str:
    text = _PARENS.sub(" ", str(text or ""))
    text = text.split(",")[0]                      # "with bone and skin", "to taste"
    text = re.sub(r"^(?:freshly|fresh)\s+ground\s+", "", text, flags=re.I)
    words = text.split()
    while words and words[0].strip(".").lower() in _LEADING:
        words.pop(0)
    text = " ".join(words)
    text = re.sub(r"^of\s+", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" ,.-")


def parse_ingredient(line: str) -> Ingredient | None:
    """One ingredient line, the way a person reads it.

    '6 chicken thighs, with bone and skin' -> amount '6', item 'chicken
    thighs'; 'a handful of parsley' -> unit 'handful', item 'parsley';
    'kosher salt, to taste' -> amount '', item 'kosher salt' (the seam
    refuses it later; nothing here invents a number).
    """
    raw = str(line or "").strip().strip("*•‣·").strip()
    if not raw:
        return None
    handful = _A_HANDFUL.match(raw)
    if handful:
        item = _clean_item(handful.group(2))
        return Ingredient(item=item or handful.group(2).strip(), amount="",
                          unit=handful.group(1).lower(), raw=raw)
    match = _AMOUNT.match(raw)
    unit, amount = "", ""
    rest = raw
    if match:
        value = _to_number(match.group(1))
        if value is not None:
            amount = _num_text(value)
            rest = match.group(2)
            first, _, tail = rest.partition(" ")
            found = _unit_or_none(first)
            if found:
                unit, rest = found, tail
            elif first.lower() == "fl" and tail.lower().startswith("oz"):
                unit, rest = "fl oz", tail[2:].lstrip()
    item = _clean_item(rest)
    if not unit:
        parts = item.split()
        found = _unit_or_none(parts[0]) if parts else None
        if found:
            unit, item = found, " ".join(parts[1:])
    item = item.strip()
    if not item:
        return None
    return Ingredient(item=item, amount=amount, unit=unit, raw=raw)


def _as_lines(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _find_recipes(node) -> list[dict]:
    found: list[dict] = []

    def walk(value):
        if isinstance(value, dict):
            types = value.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(str(t).lower() == "recipe" for t in types):
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


def _author(node: dict) -> str:
    for key in ("author", "publisher"):
        value = node.get(key)
        if isinstance(value, dict):
            value = value.get("name")
        if isinstance(value, list) and value:
            first = value[0]
            value = first.get("name") if isinstance(first, dict) else first
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _creator_from(url: str) -> str:
    host = urlparse(str(url or "")).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0] if host else ""
    return label.replace("-", " ").title() if label else ""


def _title_from(text: str) -> str:
    match = MD_TITLE.search(text)
    if match:
        return match.group(1).strip()
    match = HTML_TITLE.search(text)
    if match:
        return re.sub(r"\s+", " ", HTML_TAG.sub(" ", match.group(1))).strip()
    return ""


def _meta_creator(text: str) -> str:
    match = MD_CREATOR.search(text)
    return match.group(1).strip() if match else ""


def _recipes_in_ld(text: str) -> list[dict]:
    out: list[dict] = []
    for block in LD_JSON.findall(text or ""):
        try:
            data = json.loads(unescape(block).strip())
        except ValueError:
            continue
        out.extend(_find_recipes(data))
    return out


def _text_ingredient_lines(text: str) -> list[str]:
    """The bullets under an Ingredients heading; a plain page read as text
    is still read, but only when enough bullets actually parse as
    ingredients -- a story page with a bulleted list must not become a
    recipe with four ingredients."""
    heading = ING_HEADING.search(text or "")
    if heading:
        lines: list[str] = []
        for raw in text[heading.end():].splitlines():
            if not raw.strip():
                if lines:
                    break            # the section ended at the first blank
                continue
            bullet = BULLET.match(raw)
            if bullet:
                lines.append(bullet.group(1))
            elif lines:
                break                # prose resumed
        if lines:
            return lines
    bullets = [m.group(1) for m in
               (BULLET.match(raw) for raw in (text or "").splitlines()) if m]
    parsed = [p for p in (parse_ingredient(b) for b in bullets)
              if p and (p.amount or p.unit)]
    return bullets if len(parsed) >= 2 else []


def _ladder(title: str, count: int, structured: bool) -> float:
    """How much the reader trusts what it got, in halves it can defend:
    structured data read whole; a text page with a title and enough lines;
    a text page with less."""
    if not count:
        return 0.0
    if structured:
        if title and count >= 4:
            return 0.95
        return 0.85 if title else 0.75
    if title and count >= 4:
        return 0.88
    if title:
        return 0.80
    return 0.60


def parse_page(text: str, url: str = "") -> ImportedRecipe:
    """This page's recipe: structured data first, then the text itself."""
    text = str(text or "")
    url = str(url or "")
    for candidate in _recipes_in_ld(text):
        lines = _as_lines(candidate.get("recipeIngredient")
                          or candidate.get("ingredients"))
        if not lines:
            continue
        title = str(candidate.get("name") or "").strip() or _title_from(text)
        return ImportedRecipe(
            source=url, title=title,
            creator=_author(candidate) or _creator_from(url),
            confidence=_ladder(title, len(lines), structured=True),
            ingredients=[p for p in (parse_ingredient(l) for l in lines) if p])
    title = _title_from(text)
    creator = _meta_creator(text) or _creator_from(url)
    lines = _text_ingredient_lines(text)
    if lines:
        return ImportedRecipe(
            source=url, title=title, creator=creator,
            confidence=_ladder(title, len(lines), structured=False),
            ingredients=[p for p in (parse_ingredient(l) for l in lines) if p])
    return ImportedRecipe(
        source=url, title=title, creator=creator, confidence=0.0,
        note="no ingredient section on this page", ingredients=[])


def _fetch(url: str, timeout: float = 20.0) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def import_recipe(url: str, fetch=None) -> ImportedRecipe:
    """One link's recipe, or a named reason there is none."""
    reader = fetch or _fetch
    url = str(url or "")
    try:
        text = reader(url)
    except Exception as exc:              # the network is the one open edge
        return ImportedRecipe(
            source=url, note=f"could not read this link: {exc}")
    try:
        return parse_page(text, url)
    except Exception as exc:
        return ImportedRecipe(
            source=url, note=f"could not read this link: {exc}")
