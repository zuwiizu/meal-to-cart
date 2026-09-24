from meal_to_cart.recipes import load_import, parse_recipe, title_from_html

# The shape most recipe blogs publish, and the shape of a @graph, and a page
# with no recipe at all. All inline so the suite stays offline.
PAGE = """
<html><head><title>Fallback Title</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Weeknight Dal",
 "recipeYield":"4 servings",
 "recipeIngredient":["1 cup red lentils","2 tbsp olive oil","1 tsp cumin",
                     "1 onion, diced","3 cloves garlic"]}
</script></head><body>hi</body></html>
"""

GRAPH_PAGE = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"A Food Blog"},
  {"@type":"Recipe","name":"Sheet Pan Chicken","recipeIngredient":["chicken thighs","2 lemons"]}
]}
</script></head></html>
"""

NO_RECIPE = "<html><head><title>Just a Blog Post</title></head><body>no recipe</body></html>"


def test_it_reads_a_plain_schema_org_recipe():
    recipe = parse_recipe(PAGE, url="https://example.com/dal")
    assert recipe is not None
    assert recipe.title == "Weeknight Dal"
    assert recipe.servings == "4 servings"
    assert "1 cup red lentils" in recipe.ingredients
    assert len(recipe.ingredients) == 5
    assert recipe.source == "example.com"
    assert recipe.ok


def test_it_finds_a_recipe_nested_in_a_graph():
    recipe = parse_recipe(GRAPH_PAGE, url="https://example.com/chicken")
    assert recipe is not None
    assert recipe.title == "Sheet Pan Chicken"
    assert recipe.ingredients == ["chicken thighs", "2 lemons"]


def test_a_page_without_a_recipe_is_none_not_a_guess():
    assert parse_recipe(NO_RECIPE) is None


def test_malformed_json_is_skipped_rather_than_raising():
    broken = '<script type="application/ld+json">{not json}</script>'
    assert parse_recipe(broken) is None


def test_the_generic_fallback_title_is_available_separately():
    assert title_from_html(NO_RECIPE) == "Just a Blog Post"


def test_a_comma_inside_an_ingredient_does_not_split_it():
    """'1 onion, diced' is one line. Splitting it invented a phantom ingredient."""
    recipe = parse_recipe(PAGE)
    assert recipe is not None
    assert "1 onion, diced" in recipe.ingredients
    assert "diced" not in recipe.ingredients


def test_a_semicolon_list_is_split_into_lines():
    html = ('<script type="application/ld+json">{"@type":"Recipe","name":"X",'
            '"recipeIngredient":"salt; 2 eggs; flour"}</script>')
    recipe = parse_recipe(html)
    assert recipe is not None
    assert recipe.ingredients == ["salt", "2 eggs", "flour"]


def test_import_reads_the_shape_the_agent_produces_for_social_video(tmp_path):
    path = tmp_path / "import.json"
    path.write_text("""{"recipes":[
      {"url":"https://tiktok.com/@x/video/1","title":"Gochujang Noodles",
       "source":"tiktok","ingredients":["udon","gochujang","2 tbsp soy sauce"]},
      {"url":"https://x/empty","title":"No Ingredients","ingredients":[]}
    ]}""")
    recipes = load_import(str(path))
    assert len(recipes) == 1
    assert recipes[0].title == "Gochujang Noodles"
    assert "gochujang" in recipes[0].ingredients
