"""Fail the build if a private term reaches a public artifact.

The rule is not "try not to publish personal details". It is "the build fails if you
do". Terms live in a gitignored file so this source file -- which is itself public --
never has to name the thing it is protecting:

    data/private-terms.txt          real terms, gitignored, one substring per line
    data/private-terms.example.txt  what the format looks like

Address, email and cookie-value shapes are checked unconditionally, because those are
patterns rather than words.

    python -m meal_to_cart.guard [paths...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMS_FILE = ROOT / "data" / "private-terms.txt"

# Named separately so the pattern below stays readable and this file never has to
# embed a quote character inside a character class.
_COOKIE = r"sessionid|_pxvid|pxcts|bstc|_astc"

SHAPES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"), "an email address"),
    (re.compile(r"\b\d{2,6}\s+[A-Z][a-z]+\s+"
                r"(?:St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Dr|Drive|Blvd|Ct|Way)\b"),
     "a street address"),
    # An assignment, not a mention: naming Walmart's bot-wall cookies in prose is
    # the explanation. A quoted key or value is the leak.
    (re.compile(r'"(' + _COOKIE + r')"\s*:|:\s*"(' + _COOKIE + r')"'),
     "a session cookie value"),
    (re.compile(r"\b\d{5}(?:-\d{4})?\b(?=[^\d]*\b(?:zip|postal)\b)", re.I),
     "a postal code"),
]

SKIP_PARTS = {".git", "__pycache__", "node_modules", ".venv", "dist"}


def load_terms(path: Path | None = None) -> list[str]:
    source = path or TERMS_FILE
    if not source.exists():
        return []
    return [
        line.strip().lower()
        for line in source.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def scan(paths, terms: list[str] | None = None) -> list[tuple[str, str]]:
    """Return (file, what matched) for every violation."""
    active = load_terms() if terms is None else [t.lower() for t in terms]
    hits: list[tuple[str, str]] = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())
        for f in files:
            if any(part in SKIP_PARTS for part in f.parts):
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            low = text.lower()
            hits.extend((str(f), "a private term") for term in active if term in low)
            hits.extend((str(f), label) for pattern, label in SHAPES if pattern.search(text))
    return hits


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    targets = [Path(a) for a in args] or [ROOT]
    terms = load_terms()
    hits = scan(targets)
    if hits:
        for path, what in hits:
            try:
                rel = Path(path).relative_to(ROOT)
            except ValueError:
                rel = Path(path)
            print(f"BLOCKED: {rel} contains {what}", file=sys.stderr)
        print(f"\npublish guard failed: {len(hits)} violation(s). "
              f"Add a missing term to {TERMS_FILE.name}, then run again.",
              file=sys.stderr)
        return 1
    print(f"publish guard: clean ({len(terms)} private term(s), "
          f"{len(SHAPES)} secret shapes, {len(targets)} path(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
