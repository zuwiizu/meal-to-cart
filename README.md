# Meal-to-Cart

Turns a weekly dinner plan into a proposed Walmart cart — every line matched to a
real product, priced, and shown to a human — then stops before payment.

A household here plans seven dinners every week from a recipe corpus, which produces a
shopping list of about 50 lines. Every one of those lines then gets retyped into a
grocery site by hand. This closes that last gap: plan → list → cart, with a person
approving each line and paying themselves.

The wizard half lives at [zuwiizu/meal-to-cart-app](https://github.com/zuwiizu/meal-to-cart-app):
a brand-new user pastes recipe links, answers one card about their week, and gets back
their own plan, their own list and their own cart link. It imports this package and pins
its runtime API in its own test suite; the two repos move together.

---

## Quickstart (no credentials needed)

```bash
git clone https://github.com/zuwiizu/meal-to-cart && cd meal-to-cart
uv run --extra dev pytest -q                      # the suite, offline

# one link -> one dinner -> the whole pipeline, live search included:
uv run meal-to-cart --link "https://www.skinnytaste.com/air-fryer-chicken-thighs/"

# the exact run the wizard drives (app repo cloned next to this one):
MTC_ROOT=../meal-to-cart-app uv run meal-to-cart --profile demo \
  --link "https://www.skinnytaste.com/air-fryer-chicken-thighs/"
```

The run prints the week, every line with its aisle and amount, every refusal **by name
and reason**, and a cart link only when nothing is left unnamed. There is no checkout;
payment is yours.

---

## Architecture

```
  recipe links ─► importer ─► mealplan (rules → week → list → buys) ─┐
                                                                     ├─► resolve
  profile: values, rules, stores ────────────────────────────────────┘   (product | named refusal)
                                                                          │
                                   cart link ◄─ gateway ◄─ match ◄─ walmart (1 GET)
```

| Piece | What it does |
| --- | --- |
| `importer.py` | A recipe link → ingredient lines. The page's own JSON-LD first, plain text second, a named note when neither. Never invents an amount. |
| `mealplan/rules.py` | The profile's own rules: reject bars, review flags, phrased exceptions ("peanut" is not "peanut butter"). |
| `mealplan/planner.py` | Recipes → a week. One recipe at most once per week; a dashed expectation becomes a note, never a silent repeat. |
| `mealplan/grocery.py` | The week → one line per purchase; amounts add up only when both were stated. |
| `mealplan/shopping.py` | Lines → buys. Drops what no cart could hold (equipment, water, sentences) and names every drop. |
| `walmart.py` | The store's search page **as published**: one GET, one embedded JSON blob. Raises rather than guessing from markup. |
| `match.py` | Scores tiles. Below 0.70 the line is refused with the reason. Pure functions. |
| `cart.py` | Searches; every answer is stamped onto its own line. |
| `resolve.py` | **The seam**: a line becomes a product or a named refusal. Never searches on its own. |
| `gateway.py` | The cart link. Refuses an empty cart and a missing store; there is still no code path that pays. |
| `guard.py` | Fails the build if a private term reaches a published file. |

`normalize.py` and `match.py` are pure, so the interesting logic runs without a network.
`walmart.py` is the only module that talks to the store, so a change there breaks one file.

---

## The first build — what broke (kept as the record)

This is the honest part, and it is most of the first build.

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

## The rebuild (current code)

The first build drove a real browser through an MCP server and paid for it in CAPTCHAs
and cookie fingerprints (above). The rebuild reads the store's **search page the way the
page was built to be read**: it is a Next.js app, and its results ship as an embedded
`__NEXT_DATA__` JSON blob. One GET per query. No browser, no session, no login, no
stealth — the version string that decided everything above is simply gone.

Two failures were found live during the rebuild, and both are real:

- **A comma hid the phrase.** `" garlic powder "` failed inside `Garlic Powder, 3.4 oz`,
  so a perfect product scored 0.26 and was refused. Fixed with word-run matching; the
  same fix stops `case` firing inside "Casero" and lets `lemons` meet `lemon`.
- **The ads pushed food off the shelf.** `lemon` was refused because the first five
  tiles were an enhancer, lemonades and juice packets — and tile six was
  `Fresh Lemons, 2 lb Bag` at 0.85. The shelf is now ten wide.

What is still refused, on purpose: the real recipe asks for "dried herbs (such as herbes
de provence or dried oregano)". The store sells no product called "herbs", and every
candidate is a specific herb the recipe did not name. The pipeline refuses **by name**
rather than guessing. A named hole beats a wrong item in a cart.

The full account with commands and output is `BUILD_LOG.public.md` §6, and the wizard
end-to-end is the app repo's `SETUP.md` and `VIDEO.md`.

---

## Recipes from links

Most recipe sites already publish the recipe in machine-readable form — a
`schema.org/Recipe` block in a JSON-LD script tag — so the default import is a JSON
parse. No model, no API key, no HTML guessing. Measured live: a Skinnytaste page returns
title, creator, 8 ingredients and confidence 0.95 in about a second. When a site blocks
non-browser fetches, the import says so by name instead of guessing.

---

## Safety

- The run **never calls checkout**. There is no code path that pays, and the cart link
  opens for review in your own browser.
- Below 0.70 confidence an item is **refused by name**, never added — a wrong item costs
  more than a question.
- A cart link is rendered only when **nothing** is left unnamed.
- `python -m meal_to_cart.guard` must pass before publishing.

## Layout

```
src/meal_to_cart/   importer, profile, household, resolve, gateway, aggregate, cli,
                    mealplan/ (rules, planner, grocery, shopping, stores),
                    walmart, match, cart, normalize, guard
tests/              the suite, with a committed recipe fixture
data/               sample/, rules.public.json, extras.json
prompts/            the prompts that produced the first build, in order
scripts/, vendor/, site/    the first build's setup, vendored server and demo page
```
