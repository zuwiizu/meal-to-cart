import json

from meal_to_cart.load import load_shopping
from meal_to_cart.normalize import canonical
from meal_to_cart.pantry import candidates, filter_buys, group_for, load_catalog
from meal_to_cart.store import Store

REAL = "data/sample/shopping.sample.json"


def test_canonical_folds_plurals_without_mangling_words_that_end_in_s():
    assert canonical("small onion") == canonical("to 1/2 cup onions") == "onion"
    assert canonical("roma tomatoes") == "roma tomato"
    assert canonical("fingerling potatoes") == "fingerling potato"
    # ...and these must survive untouched.
    assert canonical("hummus") == "hummus"
    assert canonical("couscous") == "couscous"
    assert canonical("asparagus") == "asparagus"


def test_the_catalog_covers_what_kitchens_actually_stock():
    catalog = load_catalog()
    for staple in ("salt", "olive oil", "flour", "sugar", "onion", "garlic",
                   "soy sauce", "mayonnaise", "rice", "eggs"):
        assert canonical(staple) in catalog, staple


def test_it_only_asks_about_items_this_week_needs():
    buys = load_shopping(REAL)
    catalog = load_catalog()
    asked = candidates(buys, catalog)
    asked_keys = {canonical(b.item) for b in asked}
    list_keys = {canonical(b.item) for b in buys}
    assert asked_keys <= list_keys
    assert "onion" in asked_keys
    assert not [k for k in asked_keys if k == "saffron"]


def test_a_known_answer_is_not_asked_again(tmp_path):
    buys = load_shopping(REAL)
    catalog = load_catalog()
    with Store(tmp_path / "state.db") as store:
        first = candidates(buys, catalog, store.pantry())
        store.set_pantry("onion", "have")
        second = candidates(buys, catalog, store.pantry())
    assert len(second) == len(first) - 1
    assert "onion" not in {canonical(b.item) for b in second}


def test_every_line_for_one_ingredient_is_a_single_purchase():
    """'small onion', 'to 1/2 cup onions' and 'onions' are one bulb in one drawer."""
    buys = load_shopping(REAL)
    onion_lines = [b for b in buys if canonical(b.item) == "onion"]
    assert len(onion_lines) == 1, [b.item for b in onion_lines]


def test_answering_have_removes_that_item_from_the_list(tmp_path):
    buys = load_shopping(REAL)
    with Store(tmp_path / "state.db") as store:
        store.set_pantry("onion", "have")
        keep, have = filter_buys(buys, store)
    assert {canonical(b.item) for b in have} == {"onion"}
    assert len(keep) == len(buys) - len(have)


def test_answering_need_keeps_it_on_the_list(tmp_path):
    buys = load_shopping(REAL)
    with Store(tmp_path / "state.db") as store:
        store.set_pantry("onion", "need")
        keep, have = filter_buys(buys, store)
    assert not have
    assert keep == buys


def test_answers_persist_across_connections(tmp_path):
    db = tmp_path / "state.db"
    with Store(db) as store:
        store.set_pantry("cumin", "need")
    with Store(db) as store:
        assert store.pantry()["cumin"] == "need"


def test_group_lookup_traces_an_item_to_its_shelf():
    catalog = load_catalog()
    assert group_for("to 1/2 cup onions", catalog) == "Keeps well in the cupboard"
    assert group_for("tablespoon yellow mustard", catalog) == "Condiments and sauces"
    assert group_for("something invented", catalog) == "Other"
