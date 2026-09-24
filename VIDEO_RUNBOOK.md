# Video runbook — 8 minutes, self-narrated

Own voice. Screen recording with a phone-camera insert is fine; what matters is that the
demo is on real inputs and the failure is shown honestly.

## Before you hit record

```bash
cd meal-to-cart
./scripts/setup_mcp.sh                      # only if the machine is fresh
rm -f .cache/home/.striderlabs/walmart/cookies.json
./.venv/bin/python -m pytest tests/ -q      # should be green
```

Open in tabs: this runbook, `data/sample/shopping.sample.json`, `BUILD_LOG.public.md`,
a terminal at the repo root, and the deployed page.

## Shot list

| Time | On screen | Say |
| --- | --- | --- |
| 0:00–0:40 | The plan markdown, then the 68-line shopping list | "Seven dinners a week from a 113-recipe corpus. That produces this list. Every line gets retyped into a grocery site by hand. The planning is solved; the last mile is not." |
| 0:40–1:30 | The shopping list, scrolled slowly | "Look at what the planner thinks is an item: *juice of 2 large limes*, with a stray bracket. *Teaspoon cinnamon* and *teaspoon cinnamon, ground*, on separate lines. Three separate garlic lines." |
| 1:30–2:30 | `BUILD_LOG.public.md` §3.1 | "First decision: there's no public Walmart cart API. Everything official is partner-gated. So the cart has to be a browser, which is what caused every problem after this." |
| 2:30–4:00 | §3.6 and §3.7, then the bisect table | "The server ran, the browser worked, and search returned nothing. I wrote a plain script against the same URL and got 39 product cards. So the difference was in the server's own configuration. I changed one thing at a time: launch flags, viewport, geolocation, stealth script. All red herrings." |
| 4:00–4:40 | The bisect table, zoomed | "It was one string. The package ships Chromium 153 and claims to be Chrome 120. Walmart detects the lie and serves a CAPTCHA. Chrome 131 fails too; 153 returns 21 cards." |
| 4:40–5:30 | `scripts/patch_mcp.py` running twice | "The fix reads the real version off the bundled browser rather than hardcoding 153, and it fails loudly if upstream changes the string. Run it twice and it's a no-op." |
| 5:30–6:30 | `normalize.py` tests running | "Second failure: prose isn't a product. Every one of these test cases is a real line from the list. The three garlic lines collapse to one bulb." |
| 6:30–8:00 | `meal-to-cart --limit 8 --yes` live | Real searches, real SKUs, real prices, items going into a real cart. Narrate what is happening, including any block and the session rotation. |
| 8:00–8:40 | The Walmart cart page | "Here's the cart. It stops here. There is no code path that pays — the run ends and waits for a person." |
| 8:40–9:20 | The deployed page | "The public artifact is static, so it always works. Live mode reaches the agent over a tunnel when the agent is running. And the guard fails the build if a private term ever reaches a published file." |

## Two things not to do

- Do not read the code aloud line by line. Describe the decision and the evidence.
- Do not skip the failure to save time. The failure is the most credible part of the video.
