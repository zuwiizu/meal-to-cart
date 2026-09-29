"""The household's side of the engine: a week out of recipes.

rules decides what the profile's own rules bar or flag; planner turns
recipes into days; grocery merges the week into one line per purchase;
shopping turns lines into buys (and names what no cart can hold); stores
reads the profile's shops by key. The app repo imports exactly this package
to get the same plan the household's own run makes.
"""
from __future__ import annotations

__all__ = ["grocery", "planner", "rules", "shopping", "stores"]
