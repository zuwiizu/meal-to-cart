"""Every case here is a real line from the pipeline's shopping.json."""
import pytest

from meal_to_cart.normalize import is_filler, normalize_query, pack_hint


@pytest.mark.parametrize("raw,expected", [
    ("tablespoon fresh chives", "chives"),
    ("tbsp dried mint", "dried mint"),
    ("juice of 2 large limes )", "limes"),
    ("to 1/2 cup onions", "onions"),
    ("to 3 tbsp each fresh parsley", "parsley"),
    ("lbs flank or skirt steak", "skirt steak"),
    ("pound boneless lamb loin or boneless leg of lamb", "leg of lamb"),
    ("pound chicken breast cut in half", "chicken breast"),
    ("pound lean ground beef", "ground beef"),
    ("(15oz tomato sauce)", "tomato sauce"),
    ("1% buttermilk", "buttermilk"),
    ("teaspoon cinnamon, ground", "cinnamon"),
    ("teaspoon cinnamon", "cinnamon"),
    ("medium garlic cloves", "garlic"),
    ("garlic cloves", "garlic"),
    ("large zucchini", "zucchini"),
    ("teaspoon lemon", "lemon"),
    ("10 cups water or chicken stock", "chicken stock"),
    ("salmon fillets", "salmon fillets"),
    ("shredded colby jack cheese", "shredded colby jack cheese"),
])
def test_normalize_real_lines(raw, expected):
    assert normalize_query(raw) == expected


@pytest.mark.parametrize("raw", ["10 cups water", "to 3 cups boiling water", "water"])
def test_water_is_never_a_product(raw):
    assert is_filler(raw)


@pytest.mark.parametrize("qty,expected", [
    ("0.5 cup", "small"),
    ("2 cups", "standard"),
    ("1 lb", "standard"),
    ("as needed", None),
    ("", None),
])
def test_pack_hint(qty, expected):
    assert pack_hint(qty) == expected
