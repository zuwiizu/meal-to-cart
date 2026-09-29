"""A week of dinners out of the recipes on hand, under the profile's rules.

The planner is deliberately small and deliberately visible. One rule does
most of the work: a recipe is planned at most once per week. A week built
from one link is therefore ONE dinner and a stated reason -- never the same
dinner five times dressed up as a plan. Every dashed expectation becomes a
note a person can read; every barred recipe becomes a verdict, not a
silence.
"""
from __future__ import annotations

from .rules import REJECT, REVIEW, Ruleset

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")


def _words(prefs, name: str) -> list[str]:
    values = getattr(prefs, name, None) or []
    return [str(v).strip().lower() for v in values if str(v).strip()]


def _affinity(recipe: dict, likes: list[str], dislikes: list[str]) -> int:
    """How much this recipe leans toward the stated likes; stable ordering
    otherwise (the sort is stable, so equal recipes keep file order)."""
    haystack = " ".join(
        [str(recipe.get("title") or "")]
        + [str(ing.get("item") if isinstance(ing, dict) else ing)
           for ing in recipe.get("ingredients") or []]
    ).lower()
    score = sum(2 for word in likes if word and word in haystack)
    score -= sum(3 for word in dislikes if word and word in haystack)
    return score


def plan_week(recipes: list[dict], ruleset: Ruleset, prefs, days: int = 5) -> dict:
    """The week: days, notes, rejected and review.

    "review" is not "rejected": a review recipe is held back from the
    automatic plan and reported for a human, because the profile asked for
    a look, not for the recipe to be barred. A rejection is barred outright
    and named.
    """
    days = max(0, int(days or 0))
    rejected: list = []
    review: list = []
    eligible: list[dict] = []
    for recipe in recipes or []:
        verdict = ruleset.evaluate(recipe)
        if verdict.status == REJECT:
            rejected.append(verdict)
        elif verdict.status == REVIEW:
            review.append(verdict)
        else:
            eligible.append(recipe)

    likes, dislikes = _words(prefs, "likes"), _words(prefs, "dislikes")
    ordered = [eligible[i] for i in sorted(
        range(len(eligible)),
        key=lambda i: (-_affinity(eligible[i], likes, dislikes), i))]

    notes: list[str] = []
    planned: list[dict] = []
    used: set[int] = set()
    noted = False
    for index in range(days):
        day = WEEKDAYS[index % len(WEEKDAYS)]
        pick = next((r for r in ordered if id(r) not in used), None)
        if pick is not None:
            used.add(id(pick))
            planned.append({"day": day, "recipes": [pick]})
        else:
            planned.append({"day": day, "recipes": []})
            if not noted:
                noted = True
                notes.append(
                    f"{day}: nothing left to plan -- a recipe is planned at "
                    f"most once per week, so one link is one dinner, never "
                    f"the same dinner back to back. Bring another link to "
                    f"fill the week.")
    for verdict in rejected:
        notes.append(f"{verdict.title}: barred by the profile's own rule "
                     f"({verdict.explain()})")
    for verdict in review:
        notes.append(f"{verdict.title}: held back for a human look "
                     f"({verdict.explain()})")
    if recipes and not eligible and not review:
        notes.append("every recipe on hand was barred by the profile's "
                     "rules; there is nothing to plan this week.")
    return {"days": planned, "notes": notes, "rejected": rejected,
            "review": review}
