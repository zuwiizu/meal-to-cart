"""The readers with no profile named.

The household's own run starts from the household's defaults instead of a
named profile: data/household.defaults.json under the profile root. The app
repo ships no such file -- deliberately -- so load() returns {} there, and a
reader that quietly found one would be the private/public split failing.

preferences() is the single conversion point between a profile's values file
and the planner's words. It reads likes and dislikes exactly as written,
stripped of surrounding whitespace and nothing else: a preference is the
household's own sentence, not a synonym this engine substituted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import profile


@dataclass
class Prefs:
    """A profile's stated likes and dislikes, as written."""
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)


def defaults_path():
    return profile.root() / "data" / "household.defaults.json"


def load() -> dict:
    """The household defaults, or {} when this root has none."""
    path = defaults_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def preferences(name: str) -> Prefs:
    """The named profile's likes and dislikes; empty when it stated none."""
    path = profile.values_path(name)
    if not path.is_file():
        return Prefs()
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return Prefs()
    raw = (data.get("preferences") or {}) if isinstance(data, dict) else {}

    def _words(values) -> list[str]:
        return [str(v).strip() for v in (values or []) if str(v).strip()]

    return Prefs(likes=_words(raw.get("likes")),
                 dislikes=_words(raw.get("dislikes")))
