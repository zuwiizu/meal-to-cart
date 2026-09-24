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
| `pantry.py` | Asks which staples you already own, and remembers, so it asks once and not weekly. |
| `store.py` | SQLite. Pantry answers, saved recipe links, and every run's outcome. |
| `counsel.py` | Optional local advisors (Laya for verdicts, Jev for ranking). No-ops when unconfigured. |
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

## The cupboard problem

The planner already prints a cupboard check, then ignores it: the shopping list still
contains all fifteen seasonings. So they get bought every week, or deleted by hand every
week.

`meal-to-cart --pantry` asks about only the staples *this week's plan actually needs* —
eight questions for the sample week, not a hundred and twenty — and stores the answers.

```
$ meal-to-cart --pantry
8 item(s) this week's plan needs could already be in your kitchen.
Answer once and it stops asking. Enter = you need to buy it.

  [Keeps well in the cupboard] already have garlic? [y/N] y
  [Keeps well in the cupboard] already have onion? [y/N] y
  [Dry goods] already have tomato sauce? [y/N]
  ...

pantry: 8 answer(s) saved to state.db. 8 total.

$ meal-to-cart --pantry
pantry: nothing new to ask about (8 answers already stored)
```

The second run is silent, and afterwards the shopping list simply omits them. Answering
"yes" to `onion` removes every line that means onion, because `small onion`,
`to 1/2 cup onions` and `onions` are one bulb in one drawer — that is what
`canonical()` in `normalize.py` exists for.

State lives in one gitignored SQLite file: pantry answers, saved recipe links, and what
each week's run proposed and what you approved.

## Laya and Jev

Both are optional local advisors, reached over the same MCP transport `walmart.py`
already uses. `counsel.py` has a null implementation, so with nothing configured the app
runs on its built-in scorer and every call site stays free of "is it configured" branches.

They do **not** speed up the cart path. That path is limited by Walmart's request rate,
not by thinking, so no amount of local inference changes it. What they remove is the API
key, and that is the thing that actually blocks an average user.

They are worth wiring for quality. Measured on this project's worst case:

```
jev_rank("fresh dill herb, a bunch, for garnish")
  Fresh Dill, 0.75 oz Clamshell                     3.74
  Dill Pickle Flavored Potato Chips                 0.70
  OH SNAP! Dilly Bites Dill Pickle Snack Pack       0.69

laya_decide("tool_risk", {action: "add_to_cart", credentials_involved: true})
  verdict "ask_human" (p=0.841)
```

Token overlap gave the snack pack 1.00 — the highest score the system can give. Jev put
it last, in 438ms, for $0.000025. And Laya independently arrives at "ask a human" for a
live cart write, which is the stance the whole design is built around.

Wire them with:

```bash
MEAL_TO_CART_COUNSEL_CMD="npx -y your-advisor-mcp" meal-to-cart --live
```

## Safety

- The agent **never calls checkout**. There is no code path that pays.
- Below 0.70 confidence an item is **flagged, never added** — a wrong item costs more
  than a question.
- A non-interactive run declines anything it cannot ask about (`EOFError` is not consent).
- Credentials and address live only in a gitignored `.env`.
- `python -m meal_to_cart.guard` must pass before publishing.

## Layout

```
src/meal_to_cart/   normalize, match, cart, pantry, store, counsel, walmart, guard, server
data/               extras.json, rules.public.json, sample/
site/               the static demo page (demo mode always works; live mode via tunnel)
scripts/            setup_mcp.sh, patch_mcp.py, probe_mcp.py
prompts/            the prompts that produced this, in order
docs/plans/         the implementation plan
```
