# Discovery prompts

The prompts that produced the spec, in order. Reproduced as sent, with personal health
context redacted — see the note at the end for why that is enforced by the build rather
than by memory.

## 1. The starting ask

```
lets make a meal plan to grocery list to actual shopping cart building process via walmart
check this meal plan and ill let you know what we need to buy
also [personal dietary context — redacted] so i want fruits and snacks easy stuff
and easy lunches and stuff too
let work together /writing-plans lets build a prd but first /grill-me
```

The redacted clause became the household ruleset in `data/rules.public.json`, expressed as
generic food-safety ids: `high-mercury-fish`, `raw-or-undercooked`, `soft-cheese-check`,
`raw-sprouts`, and the standing exclusions of pork, alcohol and shellfish.

## 2. Grilling round 1 — find the constraint

```
Before we write anything down: what exactly are you doing today, step by step, when this
list reaches you? Which store, which device, and which part of it do you actually hate?

Then: what would have to be true for you to trust a machine to put things in a cart for
you? What must it never do without asking?
```

This is what produced the approval gate, and the decision that payment is never automated.

## 3. Grilling round 2 — surface the real rules

```
Walk me through the last five things you decided NOT to buy, and why. I care about the
ones that were not about taste: the ones about safety, about the household, about what is
already in the cupboard.

Also: how often do you buy the same thing twice in a month? Which items are "always buy"
versus "only when a recipe demands it"?
```

This is what produced the extras list and the cupboard check — and the discovery that the
planner's own staple rule only exact-matches, so `teaspoon kosher salt` survives it.

## 4. Grilling round 3 — the frontier

```
Two things I still cannot decide without you.

One: this list is 50 lines and your week is not 50 products. Am I merging lines that
describe the same purchase (three garlic lines, one bulb), or am I keeping them separate
because the recipe wants them separate?

Two: your meal plan says what is for dinner. It says nothing about the other two meals,
snacks, fruit, or drinks — which is most of what you actually carry home. Do I invent
those, or do you hand me the list?
```

Answer: merge them, and hand over the list. Both answers are in the code — `dedupe()` in
`load.py`, and `data/extras.json`.

## 5. The correction that became a build gate

The instruction was simply: **no personal health context in any public artifact, anywhere,
including the demo.** Not "be careful" — an absolute.

That turned a framing choice into an enforced gate. `src/meal_to_cart/guard.py` scans every
published file for the banned terms and relevant shapes (address fragments, email
addresses, session cookie names) and exits non-zero. It is wired into the release check,
and it earned its place immediately: the first run of the guard blocked this very file,
because the verbatim opening prompt contained the personal context.

> The rule is not "try not to publish personal details". It is "the build fails if you do."
