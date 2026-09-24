"""The guard is tested with synthetic terms and assembled-at-runtime fixtures, so
this public file never contains the shapes it is checking for."""
from pathlib import Path

from meal_to_cart.guard import load_terms, scan

FAKE = ["widgetco", "zorbulin"]

# Built at runtime so the guard's own source scan does not match them.
AT = chr(64)
EMAIL = "someone" + AT + "example.com"
STREET = "12160" + " Somewhere " + "Lane"
COOKIE = "session" + "id"


def test_guard_flags_a_planted_term(tmp_path):
    planted = tmp_path / "leak.md"
    planted.write_text("this mentions WIDGETCO plainly")
    hits = scan([planted], terms=FAKE)
    assert hits and hits[0][0] == str(planted)


def test_guard_flags_a_planted_email(tmp_path):
    planted = tmp_path / "leak.md"
    planted.write_text("write to " + EMAIL + " about it")
    assert any("email" in what for _, what in scan([planted], terms=FAKE))


def test_guard_flags_a_planted_street_address(tmp_path):
    planted = tmp_path / "leak.md"
    planted.write_text("ship it to " + STREET + " today")
    assert any("address" in what for _, what in scan([planted], terms=FAKE))


def test_guard_flags_a_session_cookie_name(tmp_path):
    planted = tmp_path / "cookies.json"
    planted.write_text('{"name": "' + COOKIE + '", "value": "abc"}')
    assert any("cookie" in what for _, what in scan([planted], terms=FAKE))


def test_clean_files_pass(tmp_path):
    fine = tmp_path / "fine.md"
    fine.write_text("a normal sentence about groceries and recipes")
    assert scan([fine], terms=FAKE) == []


def test_the_guard_has_terms_configured():
    """If the gitignored term file is missing, the guard silently protects nothing."""
    assert load_terms(), "data/private-terms.txt is missing or empty"


def test_the_public_rules_use_generic_ids_only():
    import json

    rules = json.loads(Path("data/rules.public.json").read_text())
    ids = {r["id"] for r in rules["rules"]}
    assert "soft-cheese-check" in ids
    assert "high-mercury-fish" in ids
    assert rules["header"].startswith("HOUSEHOLD FOOD-SAFETY RULES")
    blob = json.dumps(rules).lower()
    assert not [t for t in load_terms() if t in blob]
