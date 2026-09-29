# Video runbook — 8–10 minutes, self-narrated

Own voice. Screen recording with a phone-camera insert is fine; what matters is that the
demo is on real inputs and the failure is shown honestly.

## Before you hit record

```bash
cd meal-to-cart-app && uv run --extra dev pytest -q     # green
cd ../meal-to-cart   && uv run --extra dev pytest -q    # green
```

Start the two halves (both repos checked out side by side):

```bash
cd meal-to-cart-app
uv run python -m meal_to_cart_app.agent --port 8787 &    # the agent
uv run python -m http.server 8000 --directory site &     # the page
```

Open `http://127.0.0.1:8000/`, expand **Agent — where your links are sent**, set
`http://127.0.0.1:8787`, press Save. Keep in tabs: this runbook,
`BUILD_LOG.public.md` (§3–§5 first build, §6 rebuild), and a terminal at the engine root.

## Shot list

| Time | On screen | Say |
| --- | --- | --- |
| 0:00–0:40 | The wizard page | "Seven dinners a week from a recipe corpus, then every line of the list gets retyped into a grocery site by hand. The planning is solved; the last mile is not." |
| 0:40–2:00 | Paste two real recipe links, press **Read these links** | "Each link comes back as ingredients with amounts, read from the page's own structured data — confidence 0.95, no model involved." |
| 2:00–3:00 | The card: week shape, servings, budget, allergies | "The budget is a target, never a block. Allergies get named in the reasons panel, never removed quietly." |
| 3:00–5:00 | **Build my week** (real run) | Narrate: the week, the list by aisle, and any refusal — read its reason out loud. |
| 5:00–6:00 | The cart link → the real cart page | "It stops here. There is no code path that pays; payment is a human act." |
| 6:00–7:30 | `BUILD_LOG.public.md` §6: the comma bug and the ad shelf | "Two things broke live during the rebuild. Here is exactly what changed and why the fix was principled rather than tuned to make the demo look good." |
| 7:30–8:30 | §6: the "herbs" refusal | "The recipe asks for herbs; the store sells no product called 'herbs'. Rather than pick oregano, it refuses by name. That is the product working." |
| 8:30–9:30 | §3 of the log | "The first build fought a bot wall for the largest block of the project. The rebuild removed the fight: one GET of the page's own data, no browser." |

## Two things not to do

- Do not read the code aloud line by line. Describe the decision and the evidence.
- Do not skip the failure. The failure is the most credible part of the video.
