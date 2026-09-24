from meal_to_cart.match import confidence, score
from meal_to_cart.models import Buy
from meal_to_cart.walmart import parse_search

FETa = {"item_id": "34729673",
        "title": "Frigo Crumbled Feta Cheese, 5 oz Refrigerated Plastic Cup",
        "price_text": "$3.28", "price": 3.28}

CANDIDATES = [
    FETa,
    {"item_id": "2", "title": "Athenos Traditional Feta Block 8 oz",
     "price_text": "$4.12", "price": 4.12},
    {"item_id": "3", "title": "Feta Cheese Dressing", "price_text": "$2.98", "price": 2.98},
]

RAW_SEARCH = '''Found 3 products for "feta cheese":

1. Frigo Crumbled Feta Cheese, 5 oz Refrigerated Plastic Cup
   Price: $3.28
   Item ID: 34729673
   Rating: 4.7 out of 5 stars (3669)
   URL: https://www.walmart.com/ip/Frigo-Crumbled-Feta-Cheese/34729673

2. Great Value Feta Cheese Block
   Price: $2.48
   Item ID: N/A
   Rating: N/A
   URL: https://www.walmart.com/ip/Great-Value-Feta/999
'''


def test_search_text_is_parsed_into_products():
    products = parse_search(RAW_SEARCH)
    assert len(products) == 2
    assert products[0]["item_id"] == "34729673"
    assert products[0]["price"] == 3.28
    assert products[0]["title"].startswith("Frigo Crumbled")


def test_the_literal_na_item_id_becomes_none_not_a_string():
    assert parse_search(RAW_SEARCH)[1]["item_id"] is None


def test_no_products_line_is_an_empty_list():
    assert parse_search('No products found for "zzz"') == []


def test_exact_product_wins():
    result = score(Buy(item="crumbled feta cheese", buy="0.5 cup"),
                   "crumbled feta cheese", CANDIDATES)
    assert result.item_id == "34729673"
    assert result.confidence >= 0.70
    assert result.action == "add"


def test_no_candidates_flags_instead_of_guessing():
    result = score(Buy(item="truffle honey"), "truffle honey", [])
    assert result.item_id is None
    assert result.action == "flag"
    assert result.confidence == 0.0


def test_weak_overlap_is_flagged_not_added():
    result = score(Buy(item="marcona almonds"), "marcona almonds",
                   [{"item_id": "9", "title": "Whole Raw Almonds 16 oz",
                     "price_text": "$6.99", "price": 6.99}])
    assert result.action == "flag"


def test_a_match_without_an_item_id_can_never_be_added():
    result = score(Buy(item="feta cheese"), "feta cheese",
                   [{"item_id": None, "title": "feta cheese block",
                     "price_text": "$2", "price": 2.0}])
    assert result.action == "flag"
    assert result.item_id is None


def test_a_snack_pack_is_not_a_bunch_of_herbs():
    """The exact false positive from a real run, at full token overlap."""
    cands = [{"item_id": "521946957",
              "title": "OH SNAP! Dilly Bites Dill Pickle Snack Pack, Fat Free",
              "price_text": "$2.48", "price": 2.48}]
    result = score(Buy(item="dill sprigs", buy="1 bunch", aisle="produce"),
                   "dill", cands)
    assert result.confidence < 0.70
    assert result.action == "flag"


def test_the_penalty_does_not_fire_when_the_query_asks_for_that_form():
    """'pickles' is on the shopping list, and it should match pickles."""
    cands = [{"item_id": "1", "title": "Great Value Whole Dill Pickles",
              "price_text": "$2.12", "price": 2.12}]
    assert score(Buy(item="pickles"), "pickles", cands).action == "add"


def test_a_small_recipe_amount_is_penalised_for_a_club_pack():
    buy = Buy(item="buttermilk", buy="0.5 cup")
    small = confidence("buttermilk", "Buttermilk 1 qt", buy)
    bulk = confidence("buttermilk", "Buttermilk 64 oz value pack", buy)
    assert bulk < small
