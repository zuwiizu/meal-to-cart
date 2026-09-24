import json

from meal_to_cart.load import dedupe, load_shopping
from meal_to_cart.models import Buy
from meal_to_cart.normalize import normalize_query

REAL = "data/sample/shopping.sample.json"


def test_spices_aisle_is_a_cupboard_check_not_a_purchase():
    items = load_shopping(REAL)
    assert not [i for i in items if i.aisle == "spices"]


def test_pantry_staples_are_dropped_but_real_food_survives():
    keys = [i.item for i in load_shopping(REAL)]
    joined = " | ".join(keys).lower()
    assert "salt" not in joined
    assert "olive oil" not in joined
    # ...while the pantry items that are genuinely shopping stay.
    assert "flour tortillas" in joined


def test_water_is_dropped():
    assert not [i for i in load_shopping(REAL) if "water" in i.item.lower()]


def test_seasonings_hiding_in_the_pantry_aisle_are_still_dropped():
    """The pipeline only exact-matches its staple list, so these slip through."""
    keys = {normalize_query(i.item) for i in load_shopping(REAL)}
    assert "kosher salt" not in keys
    assert "allspice" not in keys


def test_three_garlic_lines_collapse_to_one_purchase():
    """'garlic cloves', 'medium garlic cloves' and '1 head of garlic' are one buy."""
    garlic = [i.item for i in load_shopping(REAL) if normalize_query(i.item) == "garlic"]
    assert len(garlic) == 1, garlic


def test_no_two_lines_normalise_to_the_same_product():
    """The whole point of dedupe: one trip to the store, not three."""
    keys = [normalize_query(i.item) for i in load_shopping(REAL)]
    assert len(keys) == len(set(keys))


def test_dedupe_keeps_the_first_spelling_and_merges_sources():
    merged = dedupe([
        Buy(item="teaspoon cinnamon", aisle="spices", source="plan"),
        Buy(item="teaspoon cinnamon, ground", aisle="spices", source="extras"),
    ])
    assert len(merged) == 1
    assert merged[0].source == "plan+extras"


def test_sample_carries_no_personal_data():
    """The fixture is published, so check its shape rather than its words."""
    raw = json.loads(open(REAL).read())
    assert set(raw) <= {"week", "items", "pantry", "dropped"}
    allowed = {"item", "buy", "aisle", "meals", "need", "approximate", "spare"}
    for row in raw["items"]:
        assert set(row) <= allowed, set(row) - allowed
    assert chr(64) not in json.dumps(raw)
