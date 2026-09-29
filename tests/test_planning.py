"""The household's half: rules bar or flag, the planner fills a week, the
grocery merges nights, and shops turns lines into buys -- naming what no
cart could hold instead of hiding it.
"""
from __future__ import annotations

import json
from pathlib import Path

from meal_to_cart.mealplan.grocery import aggregate
from meal_to_cart.mealplan.planner import plan_week
from meal_to_cart.mealplan.rules import OK, REJECT, REVIEW, Ruleset
from meal_to_cart.mealplan.shopping import Buy, is_non_ingredient, optimize, why_dropped
from meal_to_cart.mealplan.stores import build_store_plan

RULES = [
    {"name": "shellfish", "severity": "reject", "tokens": ["shrimp", "crab"],
     "why": "allergy"},
    {"name": "wine", "severity": "reject", "tokens": ["wine"],
     "exceptions": ["wine vinegar"], "why": "no alcohol"},
    {"name": "mouldy cheese", "severity": "review", "tokens": ["blue cheese"],
     "why": "ask the household"},
]


def _recipe(title, ingredients=(), source="link"):
    return {"title": title, "source": source,
            "ingredients": [{"item": i, "qty": None, "unit": ""}
                            for i in ingredients]}


class TestRules:
    def test_a_reject_is_barred(self):
        verdict = Ruleset(RULES).evaluate(_recipe("Garlic Shrimp Pasta", ["shrimp"]))
        assert verdict.status == REJECT
        assert "shellfish" in verdict.explain()

    def test_an_exception_scrubs_the_token_it_covers(self):
        # A rule about wine must not reject the vinegar a recipe deglazes with.
        ruleset = Ruleset(RULES)
        assert ruleset.evaluate(_recipe("Wine Vinegar Chicken")).status == OK
        assert ruleset.evaluate(_recipe("White Wine Chicken")).status == REJECT

    def test_review_is_not_reject(self):
        verdict = Ruleset(RULES).evaluate(_recipe("Blue Cheese Salad"))
        assert verdict.status == REVIEW

    def test_tokens_match_whole_words_only(self):
        # "crab" must not fire inside "crabapple"...
        assert Ruleset(RULES).evaluate(_recipe("Crabapple Jelly")).status == OK


class TestPlanner:
    def test_one_link_is_one_dinner_plus_a_stated_reason(self):
        plan = plan_week([_recipe("Chicken")], Ruleset([]), None, days=5)
        planned = [day for day in plan["days"] if day["recipes"]]
        assert len(planned) == 1
        assert any("one link is one dinner" in note for note in plan["notes"])

    def test_three_links_fill_three_nights(self):
        plan = plan_week([_recipe("A"), _recipe("B"), _recipe("C")],
                         Ruleset([]), None, days=5)
        assert sum(len(day["recipes"]) for day in plan["days"]) == 3

    def test_a_barred_recipe_is_reported_never_planned(self):
        plan = plan_week([_recipe("Shrimp"), _recipe("Chicken")],
                         Ruleset(RULES), None, days=5)
        titles = [r["title"] for day in plan["days"]
                  for r in day["recipes"]]
        assert titles == ["Chicken"]
        assert plan["rejected"] and plan["rejected"][0].title == "Shrimp"
        assert "shellfish" in plan["rejected"][0].explain()
        assert any("barred" in note for note in plan["notes"])


class TestGrocery:
    def test_nights_merge_into_one_line_with_summed_amounts(self):
        days = [
            {"day": "Monday", "recipes": [{"ingredients": [
                {"item": "olive oil", "qty": 2, "unit": "teaspoon"}]}]},
            {"day": "Thursday", "recipes": [{"ingredients": [
                {"item": "olive oils", "qty": 1, "unit": "teaspoon"}]}]},
        ]
        lines = aggregate(days)
        assert len(lines) == 1
        assert lines[0].qty == 3
        assert lines[0].nights == ["Monday", "Thursday"]

    def test_an_absence_stays_an_absence(self):
        days = [{"day": "Monday", "recipes": [{"ingredients": [
            {"item": "salt", "qty": None, "unit": ""}]}]}]
        assert aggregate(days)[0].qty is None


class TestShopping:
    def test_equipment_and_water_are_dropped_by_name(self):
        lines = aggregate([{"day": "Monday", "recipes": [{"ingredients": [
            {"item": "wooden skewers", "qty": 4, "unit": ""},
            {"item": "water", "qty": 1, "unit": "cup"},
        ]}]}])
        buys, dropped = optimize([], lines)
        assert buys == []
        assert sorted(dropped) == ["water", "wooden skewers"]
        assert "not food" in why_dropped("water")

    def test_a_sentence_is_dropped_as_an_instruction(self):
        assert "instruction" in why_dropped("preheat the oven to 400")
        buys, dropped = optimize([], aggregate([{"day": "Monday", "recipes": [
            {"ingredients": [{"item": "preheat the oven to 400", "qty": None,
                              "unit": ""}]}]}]))
        assert buys == [] and dropped == ["preheat the oven to 400"]

    def test_an_unsized_line_is_kept_for_the_seam_to_refuse(self):
        lines = aggregate([{"day": "Monday", "recipes": [{"ingredients": [
            {"item": "olive oil", "qty": None, "unit": ""}]}]}])
        buys, dropped = optimize([], lines)
        assert len(buys) == 1 and buys[0].buy == "as needed"
        assert dropped == []

    def test_a_handful_becomes_a_bunch(self):
        lines = aggregate([{"day": "Monday", "recipes": [{"ingredients": [
            {"item": "parsley", "qty": None, "unit": "handful"}]}]}])
        buys, _ = optimize([], lines)
        assert buys[0].buy == "1 bunch"

    def test_there_are_exactly_two_drop_predicates(self):
        # One reads a name, the other reads a sentence; neither is an amount.
        assert is_non_ingredient("aluminum foil")
        assert not is_non_ingredient("olive oil")


class TestStores:
    def test_stops_are_read_by_key(self, tmp_path: Path):
        path = tmp_path / "stores.json"
        path.write_text(json.dumps({"stores": [
            {"key": "walmart", "name": "Demo Walmart", "storeId": "0000"},
            {"key": "target", "name": "Demo Pantry Store"},
        ]}))
        stops = build_store_plan(path)
        assert [stop.key for stop in stops] == ["walmart", "target"]
        assert stops[0].store_id == "0000"

    def test_a_missing_slots_file_is_no_stops(self, tmp_path: Path):
        assert build_store_plan(tmp_path / "nope.json") == []
