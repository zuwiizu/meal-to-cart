# Meal-to-Cart

Turns a weekly dinner plan into a proposed Walmart cart — every line matched to a
real product, priced, and shown to a human — then stops before payment.

A household here plans seven dinners every week from a recipe corpus, which produces a
shopping list of about 50 lines. Every one of those lines then gets retyped into a
grocery site by hand. This closes that last gap: plan → list → cart, with a person
approving each line and paying themselves.

---

## Quickstart (no credentials needed)

```bash
git clone <this repo> && cd meal-to-cart
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
./.venv/bin/meal-to-cart --dry-run
```

That prints the whole pipeline — load, filter, normalise, match, propose — with no
network, no login and no browser. Sample data ships in `data/sample/`.

To go live you need the Walmart MCP server and one browser download:

```bash
./scripts/setup_mcp.sh          # installs the server, the browser, and two patches
./.venv/bin/meal-to-cart --limit 5 --yes
```

`--yes` auto-approves matches so the run is non-interactive. It still cannot pay.

---

## Architecture

```
  weekly plan  ──►  shopping.json  ──┐
  (existing pipeline, unchanged)     │
                                     ├──►  normalize  ──►  match  ──►  APPROVE  ──►  cart
  extras.json (breakfast, lunch,     │      prose →       search →     a human      (stop)
  snacks, fruit, drinks)  ───────────┘      a product      a SKU       decides
```

| Piece | What it does |
| --- | --- |
| `mealplan` (external) | The existing planner. Gained one flag, `--shopping-json`, and nothing else. |
| `normalize.py` | Recipe prose into something a store search bar accepts. Pure functions. |
| `match.py` | Scores search candidates, and refuses to guess below 0.70 confidence. Pure functions. |
| `cart.py` | `build_plan` only searches. `apply` is the only writer, and it writes only what a human approved. |
| `walmart.py` | The single MCP boundary. Owns the session and every response-shape assumption. |
| `guard.py` | Fails the build if a private term reaches a published file. |

Two boundaries are deliberately narrow. `walmart.py` is the only module that touches the
network, so a change in the third-party server breaks one file. `normalize.py` and
`match.py` are pure, so the interesting logic is testable without a browser or a login.

---

## What broke

This is the honest part, and it is most of the build.

**1. There is no public Walmart cart API.** The official APIs are partner-gated, so the
cart path is browser automation through a third-party MCP server. That decision is what
created every problem below.

**2. The MCP announced itself as Chrome/120 while shipping Chromium 153.** Walmart's bot
detection answers the mismatch with a CAPTCHA instead of products. Measured on one
machine, in one minute, with only the User-Agent varying:

| User-Agent | Product cards | Page title |
| --- | --- | --- |
| `Chrome/120.0.0.0` | 0 | Robot or human? |
| `Chrome/131.0.0.0` | 0 | Robot or human? |
| `Chrome/153.0.0.0` | 21 | feta cheese - Walmart.com |

The launch flags and the injected stealth script made no difference; the version string
alone decided it. `scripts/patch_mcp.py` reads the real version off the bundled browser
and writes that into the User-Agent, so it stays true after an upgrade.

**3. A blocked page poisons the session, and rotating the browser does not fix it.** The
server saves cookies even when the page it got back is the bot wall, and those cookies
carry the block fingerprint (`_pxvid`, `pxcts`, `btc`, `bsc`, `vtc`). The obvious fix —
tear the browser down, clear the jar, start over — **does not work**, and measuring it is
what showed why: every fresh session presents the same visitor id. It is a request *rate*,
not a session. Two searches go through and then the wall comes down, every time.

The answer is to not ask twice: every search is cached, so a weekly re-run over the same
forty products costs no requests at all, and a cold run paces itself at 25 seconds a
query. `meal-to-cart --replay` rebuilds the entire plan from cache with no network.

**4. Prose is not a product.** The real list contains `juice of 2 large limes )`,
`to 1/2 cup onions`, `(15oz tomato sauce)`, `1% buttermilk`, `teaspoon cinnamon` *and*
`teaspoon cinnamon, ground`. Naive matching adds the wrong thing or nothing at all.
Normalising them, and deduping the three separate garlic lines into one bulb, is the
actual engineering.

**5. Everything assumes it owns your home directory.** `npm` cannot run at all here
(root-owned cache), `bun` refuses to start without a writable tempdir, `patchright`
wants to put 550MB in `~/Library/Caches`, and the MCP server hardcodes
`os.homedir()/.striderlabs/walmart` for its cookie jar. `scripts/setup_mcp.sh` scopes all
four inside the project.

Full evidence, including the commands and their output, is in `BUILD_LOG.public.md`.

---

## Safety

- The agent **never calls checkout**. There is no code path that pays.
- Below 0.70 confidence an item is **flagged, never added** — a wrong item costs more
  than a question.
- A non-interactive run declines anything it cannot ask about (`EOFError` is not consent).
- Credentials and address live only in a gitignored `.env`.
- `python -m meal_to_cart.guard` must pass before publishing.

## Layout

```
src/meal_to_cart/   normalize, match, cart, cli, walmart, guard, server
data/               extras.json, rules.public.json, sample/
site/               the static demo page (demo mode always works; live mode via tunnel)
scripts/            setup_mcp.sh, patch_mcp.py, probe_mcp.py
prompts/            the prompts that produced this, in order
docs/plans/         the implementation plan
```
