"""The importer: structured data first, the page's own text second, and an
honest note when it is neither. It never invents an amount -- the absence
travels to the seam, which is the only place allowed to refuse it.
"""
from __future__ import annotations

import json
from pathlib import Path

from meal_to_cart.importer import ImportedRecipe, import_recipe, parse_page

SIZED = """Title: Demo Pantry Bowls

## Ingredients
* 2 teaspoon olive oil
* 1 teaspoon kosher salt
* 1 teaspoon garlic powder
* 0.5 teaspoon black pepper
"""

LOOSE = """Title: Seasoning Only

## Ingredients
* kosher salt, to taste
* freshly ground black pepper
* olive oil
* a handful of parsley
"""

LD_HTML = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Recipe",
 "name": "Garlic Shrimp Pasta",
 "author": {"@type": "Person", "name": "A Creator"},
 "recipeIngredient": ["1 pound shrimp", "3 cloves garlic", "2 tablespoon olive oil",
                      "1 teaspoon kosher salt"]}
</script></head><body>...</body></html>
"""


def _by_item(recipe):
    return {ingredient.item: ingredient for ingredient in recipe.ingredients}


def test_a_text_page_is_read_line_by_line():
    recipe = parse_page(SIZED, "https://example.com/x")
    assert recipe.title == "Demo Pantry Bowls"
    assert recipe.confidence == 0.88
    assert recipe.note == ""
    by_item = _by_item(recipe)
    assert set(by_item) == {"olive oil", "kosher salt", "garlic powder",
                            "black pepper"}
    assert by_item["olive oil"].amount == "2"
    assert by_item["olive oil"].unit == "teaspoon"
    assert by_item["black pepper"].amount == "0.5"


def test_absent_amounts_stay_absent():
    recipe = parse_page(LOOSE, "https://example.com/y")
    by_item = _by_item(recipe)
    assert by_item["kosher salt"].amount == ""      # "to taste" is not a number
    assert by_item["black pepper"].amount == ""     # nor is silence
    assert by_item["black pepper"].item == "black pepper"
    assert by_item["olive oil"].amount == ""
    # A handful is a concrete buy the aggregator may size; still no number.
    assert by_item["parsley"].amount == ""
    assert by_item["parsley"].unit == "handful"


def test_structured_data_is_the_trusted_path():
    recipe = parse_page(LD_HTML, "https://example.com/r")
    assert recipe.title == "Garlic Shrimp Pasta"
    assert recipe.creator == "A Creator"
    assert recipe.confidence == 0.95
    by_item = _by_item(recipe)
    assert by_item["shrimp"].amount == "1"
    assert by_item["garlic"].unit == "cloves"


def test_a_page_with_no_recipe_says_so_instead_of_pretending():
    recipe = parse_page("<html><body>A story about food.</body></html>",
                        "https://example.com/z")
    assert recipe.ingredients == []
    assert recipe.confidence == 0.0
    assert "no ingredient section" in recipe.note


def test_a_link_that_cannot_be_read_is_a_named_note():
    def boom(url):
        raise OSError("boom")
    recipe = import_recipe("https://example.invalid/recipe", fetch=boom)
    assert isinstance(recipe, ImportedRecipe)
    assert recipe.ingredients == []
    assert recipe.note == "could not read this link: boom"


def test_the_committed_fixture_reads_whole():
    fixture = (Path(__file__).parent / "fixtures"
               / "recipe-skinnytaste.md").read_text()
    recipe = parse_page(fixture, "https://skinnytaste.com/example")
    assert recipe.title == "Air Fryer Chicken Thighs"
    assert len(recipe.ingredients) == 8
    assert all(ingredient.amount for ingredient in recipe.ingredients)
    assert _by_item(recipe)["parsley"].unit == "tablespoon"
    assert _by_item(recipe)["chicken thighs"].amount == "6"


def test_a_named_standin_replaces_a_bare_category_head():
    """'dried herbs (such as herbs de provence or dried oregano)': the recipe
    named its own stand-ins, and a bare category head is not a product, so
    the first stand-in is what the store is asked for. A multi-word head is
    already a name and is left alone."""
    recipe = parse_page(
        "Title: Stand-in\n\n## Ingredients\n"
        "* 0.5 teaspoon dried herbs (such as herbs de provence or dried oregano)\n"
        "* 2 pounds chicken thighs (such as boneless or bone-in)\n",
        "https://example.com/standin")
    by_item = _by_item(recipe)
    assert by_item["herbs de provence"].amount == "0.5"
    assert by_item["herbs de provence"].unit == "teaspoon"
    assert "chicken thighs" in by_item
