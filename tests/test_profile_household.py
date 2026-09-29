"""The profile root is one answer, and the household readers are lenient
in exactly the two places a missing file means "stated nothing" -- never a
missing amount, never a silently substituted value.
"""
from __future__ import annotations

import json

import pytest

from meal_to_cart import household, profile


def test_the_slot_names_are_the_contract():
    # A slot the engine never names is a feature nobody can have.
    assert {"values", "rules", "recipes", "stores"} <= set(profile.FILES)


def test_the_root_follows_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MTC_ROOT", str(tmp_path))
    assert profile.root() == tmp_path.resolve()
    assert profile.values_path("demo") == tmp_path / "profiles" / "demo" / "values.json"


def test_a_profile_that_is_not_there_is_unknown_not_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("MTC_ROOT", str(tmp_path))
    with pytest.raises(profile.UnknownProfile):
        profile.paths("nope")
    with pytest.raises(profile.UnknownProfile):
        profile.paths("../escape")


def test_available_lists_the_profiles_the_root_has(tmp_path, monkeypatch):
    monkeypatch.setenv("MTC_ROOT", str(tmp_path))
    demo = tmp_path / "profiles" / "demo"
    demo.mkdir(parents=True)
    (demo / "values.json").write_text("{}")
    (tmp_path / "profiles" / "empty").mkdir()
    assert profile.available() == ["demo"]


def test_the_household_defaults_are_absent_here_and_read_as_absent():
    # This repo ships no data/household.defaults.json: a reader that found
    # one would be the private/public split failing.
    assert household.load() == {}


def test_preferences_are_the_profiles_own_words(tmp_path, monkeypatch):
    monkeypatch.setenv("MTC_ROOT", str(tmp_path))
    demo = tmp_path / "profiles" / "demo"
    demo.mkdir(parents=True)
    (demo / "values.json").write_text(json.dumps({
        "preferences": {"likes": ["pasta", "soup"], "dislikes": ["olives"]},
    }))
    prefs = household.preferences("demo")
    assert prefs.likes == ["pasta", "soup"]
    assert prefs.dislikes == ["olives"]
    # A profile that stated nothing reads as nothing, not as someone's guess.
    assert household.preferences("someone-else").likes == []
