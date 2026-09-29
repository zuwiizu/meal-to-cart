"""Where a profile's files live -- one answer, asked the same way everywhere.

A profile is a directory under the profile root: values, rules, recipes and
store facts, one file per slot, named by FILES. The root comes from MTC_ROOT
when a caller relocates it (the app sets it to its own repo, so the two
repos can never share a profile), and falls back to this repository so the
household's own runs need no environment at all.

Nothing here caches the root: MTC_ROOT is read per call, so a caller can
move the root for this process and every reader follows. A second place that
builds profile paths by hand is the drift defect this module exists to
prevent: the writer and the reader must never mean two different files while
both look correct.
"""
from __future__ import annotations

import os
from pathlib import Path

# The slot names are the contract. A slot the engine never names is a
# feature nobody can have; the demo ships without recipes.json on purpose,
# because its recipes arrive as links.
FILES = {
    "values": "values.json",
    "rules": "rules.json",
    "recipes": "recipes.json",
    "stores": "stores.json",
}

_REPO_ROOT = Path(__file__).resolve().parents[2]


class UnknownProfile(Exception):
    """The named profile is not a directory the engine may read."""


def root() -> Path:
    """The profile root: MTC_ROOT when set, this repository otherwise."""
    env = os.environ.get("MTC_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return _REPO_ROOT


def _checked(name: str) -> str:
    name = str(name or "").strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise UnknownProfile(f"not a profile name: {name!r}")
    return name


def profile_dir(name: str) -> Path:
    return root() / "profiles" / _checked(name)


def values_path(name: str) -> Path:
    """Where this profile's values live. Does not require them to exist yet:
    the setup form saves through this same call, creating the directory."""
    return profile_dir(name) / FILES["values"]


def paths(name: str) -> dict[str, Path]:
    """Every slot's path for one profile, or UnknownProfile.

    A missing profile directory is unknown, not empty: "the file is not
    there" and "this profile does not exist" are different answers, and a
    reader that conflated them would report a stranger's profile as one that
    merely stated nothing.
    """
    directory = profile_dir(name)
    if not directory.is_dir():
        raise UnknownProfile(f"no profile directory: {directory}")
    return {slot: directory / filename for slot, filename in FILES.items()}


def available() -> list[str]:
    """The profiles this engine may read, by name, sorted."""
    base = root() / "profiles"
    if not base.is_dir():
        return []
    return sorted(
        entry.name
        for entry in base.iterdir()
        if entry.is_dir() and (entry / FILES["values"]).is_file()
    )
