# Build log

What was actually run, in order, with the output that came back. The failures are the
interesting part, so they are written up in full rather than summarised.

---

## 1. The workflow as it exists today

A household plans seven dinners a week from a recipe corpus of 113 eligible recipes, which
is filtered by a ruleset down to seven, and then flattened into a shopping list.

The list that came out of the real week of 2026-09-21:

```
7 meals planned from 113 eligible recipes
23 blocked by your restrictions
9 need a look
68 items to buy (from 76 recipe lines)
7 creator(s) on the table
```

Those 68 lines then get retyped into a grocery site by hand, item by item, every week.
The planner already knows which nights each item serves and which items are a cupboard
check rather than a purchase. None of that survives the retyping.

**The gap is not planning. It is the last mile: list → cart.**

## 2. Decisions, and why

| Decision | Why |
| --- | --- |
| Integrate with the existing planner, do not rebuild it | It encodes a ruleset, a recipe corpus, a deals feed and a history of what was already served. A rewrite throws all of that away. |
| Add exactly one output to it: `--shopping-json` | A prose shopping list cannot be matched against a catalogue. One flag, no other change, and the planner stays the source of truth. |
| Drive the browser through an MCP server rather than writing one | The cart path is the only part that needs a real logged-in browser. Keeping it behind a boundary means the fragile third-party part touches one file. |
| Split the surface: static page + local agent | A static host cannot hold a browser session or a login. The page is shareable; the agent runs where the session lives. |
| Flag below 0.70 confidence instead of guessing | A wrong item in a cart costs more than a question. |
| Stop before checkout, always | Payment is a human act. This is enforced by the absence of code, not by a setting. |

## 3. Failure log

### 3.1 No public Walmart cart API

The official Walmart APIs are partner-gated. The cart path had to become browser
automation, which is the root cause of every failure below.

### 3.2 npm cannot run on this machine at all

```
$ npm --version
EPERM: operation not permitted, mkdir '/Users/.../.npm/_cacache'
```

`~/.npm` contains root-owned files. Redirecting the cache did not help because npm also
writes its log directory. `bun` works, so everything uses `bunx`.

### 3.3 bun refuses to start: "unable to write files to tempdir"

```
$ bunx @striderlabs/mcp-walmart
error: bun is unable to write files to tempdir: PermissionDenied
```

The agent runs under a file sandbox that only writes inside the workspace. Setting
`TMPDIR` alone was not enough — bun also needs an install cache it can write to, and
`~/.bun` is outside the sandbox:

```
$ touch ~/.bun/dsh-test
touch: /Users/.../.bun/dsh-test: Operation not permitted
```

Scoping both into the project made the server start:

```
$ BUN_INSTALL_CACHE_DIR="$PWD/.cache/bun" TMPDIR="$PWD/.cache/tmp" bunx @striderlabs/mcp-walmart
Resolving dependencies
Resolved, downloaded and extracted [35]
Walmart MCP server running on stdio
```

### 3.4 The probe then failed on a browser that did not exist

Twelve tools were exposed — `add_to_cart`, `search`, `login`, `set_address`, `view_cart`,
`checkout`, and seven more — but every browser-backed call returned:

```
Error: Tool 'search' failed: browserType.launch: Executable doesn't exist at
/Users/.../Library/Caches/ms-playwright/chromium_headless_shell-1243/...
```

That is a 550MB download pointing outside the sandbox, so `PLAYWRIGHT_BROWSERS_PATH` was
scoped into the project too. The server bundles `patchright` 1.63.0, whose CLI is the
thing to run:

```
$ bunx patchright@1.63.0 install chromium
Chrome Headless Shell 153.0.8010.12 (playwright chromium-headless-shell v1243) downloaded
```

### 3.5 The session directory is hardcoded to the home directory

```
Error: Tool 'set_address' failed: EPERM: operation not permitted,
mkdir '/Users/.../.striderlabs/walmart'
```

Reading the package source shows there is no override:

```js
// dist/session.js:4
const SESSION_DIR = path.join(os.homedir(), ".striderlabs", "walmart");
```

Node resolves `HOME` before falling back to the password database, so redirecting `HOME`
for the child process scopes its cookie jar — and therefore the logged-in session —
inside the project.

### 3.6 Everything runs, and search still returns nothing

With all four path overrides in place, `set_address` worked and `search` did not:

```
=== set_address ===
Address saved locally: [redacted]
=== search ===
Error: No products found or page failed to load
```

A plain `patchright` script against the same URL, same minute, returned **39 product
cards** and live prices. So the browser worked and the server did not.

The server's search handler has a bare `catch` that hides the reason, so the first move
was to make it talk. It was waiting on a selector and timing out — on a page titled
**"Robot or human?"**. Walmart's bot wall.

### 3.7 Bisecting the bot wall down to one string

Four configurations, one change at a time, counting product cards:

```
MCP-exact      cards=0  title=Robot or human?
MCP-no-geo     cards=0  title=Robot or human?
MCP-no-args    cards=0  title=Robot or human?
mine-working   cards=21
```

That ruled out geolocation, timezone and the launch flags. Narrowing further:

```
ua153+args+st    cards=21
ua120 plain      cards=0  title=Robot or human?
ua153+stealth    cards=21
ua153+args       cards=21
ua131 plain      cards=0  title=Robot or human?
```

**The User-Agent alone decided it.** The package ships Chromium **153** and announces
itself as **Chrome/120**. Walmart detects the mismatch. The launch flags and the injected
stealth script were irrelevant the whole time.

The fix reads the real version off the bundled browser instead of hardcoding a number, so
it stays correct after an upgrade, and it fails loudly if upstream changes the string:

```
$ python3 scripts/patch_mcp.py
patch 1: user-agent Chrome/120.0.0.0 -> Chrome/153.0.0.0
patch 2: block reporting patched (bot wall now names itself)

$ python3 scripts/patch_mcp.py
patch 1: user-agent already Chrome/153.0.0.0
patch 2: block reporting already patched
```

### 3.8 A block page poisons the session permanently

Even with the correct User-Agent, the block came back. Deleting one file fixed it:

```
$ python3 -c "import json; c=json.load(open('.cache/home/.striderlabs/walmart/cookies.json')); print(len(c))"
28
   _pxvid | .walmart.com
   pxcts  | .walmart.com
   btc    | b.www.walmart.com
   bsc    | b.www.walmart.com
   vtc    | .walmart.com

$ rm cookies.json && meal-to-cart --limit 4
[add] Fresh Mini Cucumbers, 16 oz
```

Those are PerimeterX fingerprint cookies. The server saves cookies **even when the page it
got back was the bot wall**, so one detection event is reloaded by every subsequent run.

### 3.9 The fix that was wrong, and how it was caught

The first reading of the evidence was that a block is sticky for the life of one browser
session, because retrying produced the *same* block uuid twice for the same query:

```
[meal-to-cart] Walmart bot wall at ...?q=dill&uuid=591de930-b846-11f1-801d-b1a7063e02dc
[meal-to-cart] Walmart bot wall at ...?q=dill&uuid=591de930-b846-11f1-801d-b1a7063e02dc
```

So session rotation was implemented: tear the browser down, delete the cookie jar, start
again. It is a reasonable inference and it is wrong. Rotating produced a new `uuid` but
**the same visitor id**:

```
?q=dill             &uuid=8bf88ea0...&vid=897fe459-b846-11f1-8c0d-dd15c96e717f
?q=english+cucumber &uuid=a195b300...&vid=581c5209-b846-11f1-a9d5-8cc37d701ea6
?q=english+cucumber &uuid=a399e770...&vid=581c5209-b846-11f1-a9d5-8cc37d701ea6
?q=english+cucumber &uuid=c5be98a0...&vid=c4e63f7d-b846-11f1-97ab-be5305dc32f4
```

`uuid` changes every time and `vid` barely moves — and when it does move, the new value is
persisted straight back into the cookie jar. A fresh browser with an empty jar still
presents the same visitor, so rotation cannot clear the block: what Walmart fingerprints
is not the session.

Counting searches across four runs gives the actual rule:

| Run | Searches before the wall |
| --- | --- |
| `--limit 4` | 2 |
| `--limit 5 --pause 8` | 2 |
| `--limit 16 --pause 5` | 2 |
| `--limit 70 --pause 22` | 2 |

**It is a request rate, not a session.** Two searches go through, then the wall, and a
short wait resets it. No amount of browser surgery changes that.

Which means the fix is not to retry at all — it is to not ask twice.

### 3.10 Not asking twice

If the block is a rate, the engineering answer is to spend fewer requests. Two changes:

**Cache every search.** Each query is written to `.cache/search-cache.json` keyed by its
normalised form, so a second run over the same plan costs nothing. A weekly task mostly
searches the same forty products every time; only the recipe-driven lines change. The first
run pays the rate limit, every run after it is free.

**Pace the first run.** The default gap between searches is 25 seconds, with one long wait
and one retry if a block arrives anyway. Forty-five lines is then about twenty minutes of
unattended work, which is the right shape for a task that runs once a week.

And a replay mode, so the whole plan can be rebuilt from cache with no network at all:

```
$ meal-to-cart --replay
[replay] 38/103 lines matched from cache, no network used
```

This is also what makes the demo page honest: it renders the real recorded run, not a
mock-up, and it still loads instantly.

### 3.11 Prose is not a product

The real list, unfiltered:

```
'juice of 2 large limes )'          'to 1/2 cup onions'
'(15oz tomato sauce)'               '1% buttermilk'
'lbs flank or skirt steak'          'pound chicken breast cut in half'
'teaspoon cinnamon'                 'teaspoon cinnamon, ground'
'garlic cloves'  'medium garlic cloves'  '1 head of garlic'
```

Naive matching adds the wrong thing or nothing at all. Three garlic lines are one bulb.
Two cinnamon lines are one jar. `10 cups water or chicken stock` is not a product; the
stock is. Every rule in `normalize.py` exists because a real line demanded it, and every
test case is one of these strings.

The pipeline's own staple rule is also exact-string matching, so `teaspoon kosher salt`
sits in the pantry aisle and survives it. Normalising first catches it.

### 3.12 The gate that checked nothing

The privacy rule needed to be enforced by the build, so `guard.py` scans the tree and
exits non-zero on a violation. It reported clean.

It was checking nothing. The file-skip list contained `dist`, because the publish tree
lives in `dist/public` and recursion into an output directory is wasted work:

```python
SKIP_PARTS = {".git", "__pycache__", "node_modules", ".venv", "dist"}
```

So when the gate was pointed at the publish directory — the one thing it exists to check —
it matched `dist` in every path and skipped every file. The tell was an inconsistency: the
same file, byte for byte, flagged when scanned directly and clean when scanned inside the
publish tree.

```
source md5: e0e63c8f168c557f05e8c595fcf53026
public md5: e0e63c8f168c557f05e8c595fcf53026
identical: True
scan dist/public/BUILD_LOG.public.md -> []
scan BUILD_LOG.public.md            -> [('BUILD_LOG.public.md', 'an email address')]
```

Two lessons, and the second is the one that matters:

1. An excluded directory name is a hole in a gate. Narrow the skip list to things that are
   never published.
2. **A passing check is not evidence until you have watched it fail.** The gate now has a
   test that plants a violation inside `dist/`, and the release script is verified by
   planting a file in the real publish tree and confirming it exits 1.

That second check also caught a false positive worth keeping: `bunx patchright@1.63.0`
reads as an email address to a loose pattern, so the pattern now requires an alphabetic
top-level domain.

### 3.13 The test suite was spending the agent's request budget

The bring-up probe — the script that proves the MCP server exposes the four tools the
agent needs — ran as a normal test. Which meant every `pytest` invocation started a
browser and searched Walmart.

That is the same budget the agent needs for real runs, so the suite was competing with the
thing it was testing. It also made the suite take 21 seconds instead of 0.6.

```
$ pytest tests/ -q
63 passed, 1 skipped in 0.64s
```

The probe is now opt-in behind `MEAL_TO_CART_LIVE=1`, and a test asserts the default run
is offline.

The safety invariant that replaced it is better than the probe anyway: instead of checking
that a browser works, assert the thing that must never happen. `test_probe.py` now walks
every source line and fails if the word `checkout` appears anywhere outside the constant
that declares it forbidden. There is no code path that pays, and the build proves it.

### 3.14 A perfect score for the wrong product

The matcher scores a candidate by how much of the query appears in the product title.
Here is what a real run did with the line `dill sprigs`:

```
[add] dill -> OH SNAP! Dilly Bites Dill Pickle Snack Pack, Fat Free
```

Confidence **1.00**. The highest score the system can give, for a bag of candy, against a
recipe asking for a bunch of fresh herbs.

The arithmetic is not wrong. The query normalises to `dill`, which is one token, and the
title contains that token, so overlap is 1/1. A single-token query cannot express what
*kind* of thing it wants, and token overlap has no way to notice.

The fix is a form check: when the query does not itself name a processed form but the
title does, that is a different kind of product regardless of how many tokens it shares.
`snack`, `pickle`, `chips`, `sauce`, `frozen`, `candy` and about twenty others carry a
penalty that puts the score under the auto-add bar:

```
dill  x OH SNAP! Dilly Bites Dill Pickle Snack Pack  ->  0.55  flag
pickles x Great Value Whole Dill Pickles             ->  1.00  add
```

The second line is the check on the check: `pickles` is on the shopping list and must
still match pickles, so the penalty only applies when the query does **not** name the form.
Both cases are tests.

This is the failure worth showing in the video, more than the User-Agent one. The
User-Agent problem announced itself as an error. This one announced itself as success, and
it was only caught by reading the actual matched titles in a real run rather than trusting
the confidence number.

### 3.15 Splitting ingredients on every comma

The recipe importer split a semicolon-joined string into lines, and used the same
separator set when the recipe was already a clean list of ingredients. Every
`schema.org/Recipe` publishes `recipeIngredient` as a list, one ingredient per entry.

So `"1 onion, diced"` became two ingredients, `1 onion` and `diced`. A test caught it:

```
assert "1 onion, diced" in recipe.ingredients
assert "diced" not in recipe.ingredients
```

The second line is the one that matters. Without it the test passes on the mangled
output too. A comma inside an ingredient belongs to the ingredient; only a raw string
needs splitting, and only on newlines and semicolons.

## 4. What the run does now

```
$ meal-to-cart --limit 16 --yes --pause 5
16 lines to consider (0 of them extras)
cleared a stale session cookie jar
status: Not logged in. Use the `login` tool to authenticate.
  [ 1/16] add  1.00 cucumbers
  [ 2/16] add  1.00 garlic
  ...
  [ 5/16] flag 0.50 fingerling potatoes

[add ] 1.00   $2.00  cucumbers            -> Fresh Mini Cucumbers, 16 oz
[add ] 1.00   $0.00  garlic               -> Garlic Bulb Fresh Whole, Each
[flag] 0.50   $4.00  fingerling potatoes  -> Fresh Yellow Petite Potatoes, 1.5 lb Bag
[flag] 0.00       ?  dill                 -> (search failed: WalmartBlocked)

2 matched, 3 need your call
{
  "would_add": 0,
  "added": 2,
  "denied": 0,
  "skipped_flagged": 3
}

STOPPING BEFORE CHECKOUT. Payment is yours to make.
```

The last line is the point of the whole thing. The run reaches a real cart with real
products and real prices, and then it stops and hands over.

Note the flagged potato line: the match is *plausible* — "Fresh Yellow Petite Potatoes,
1.5 lb Bag" is a real, sensible substitute for fingerling potatoes — and it scored 0.50,
under the 0.70 bar, so it was flagged rather than added. That is the intended behaviour
and it is why the threshold is not tuned down to make the demo look better.

68 plan lines become about 45 after the cupboard check and dedupe, and the extras list
adds breakfast, lunch, snacks, fruit and drinks on top.

## 5. Time

| Phase | Time |
| --- | --- |
| Discovery and grilling, three rounds | ~40 min |
| PRD and implementation plan | ~35 min |
| Sandbox and MCP bring-up (3.2 – 3.5) | ~50 min |
| Bot wall bisection and the two patches (3.6 – 3.9) | ~70 min |
| Normaliser, matcher, cart builder, tests | ~60 min |
| Surface, guard, docs | ~40 min |

The bot wall ate the single largest block of time, and none of it was planned for.

---

## 6. The rebuild: the simple path (2026-09-29)

Everything above is the first build, and it stays because it is the record: the cart path
was browser automation, and the bot wall fought it at every step. The rebuild replaces
that path with a plain HTTP read of the store's own search page. One GET per query. No
browser, no MCP server, no cookie jar, no stealth script, no login. The store ships its
search results as an embedded `__NEXT_DATA__` JSON blob — the page is a Next.js app, and
that blob exists to be machine-read. When it is absent, the reader raises instead of
guessing from markup.

The engine was rebuilt to the runtime API the companion wizard app
(`zuwiizu/meal-to-cart-app`) already pins in its own tests, so both halves talk the same
shapes: importer → mealplan → gateway, with `resolve.py` as the seam. A line becomes a
product or a **named refusal**; a cart link is only rendered when nothing is left
unnamed. Retired with the rebuild: the MCP boundary, the pantry, the SQLite store, the
local-advisor module, and the old CLI surface.

### 6.1 What broke in the rebuild (live, with the store's real titles)

**Commas hid the phrase.** The scorer first checked `" garlic powder "` as a substring.
The store's best tiles say `Garlic Powder, 3.4 oz` — comma, not space — so the phrase
check failed, the row fell back to a single-token match, and a perfect product scored
0.26 and was refused. The same family of bug let `case` fire inside "Casero" (a false
bulk flag) and kept `lemons` from meeting `lemon`. Fixed by matching word runs
(punctuation cannot hide a phrase), folding plurals symmetrically on both sides, and
matching bulk words as whole words. `Garlic Powder, 3.4 oz` now scores 0.85 and adds.

**The ad block pushed real food off the shelf.** `lemon` was refused at 0.60: the first
five tiles were an enhancer, lemonades and juice packets. Tile six was
`Fresh Lemons, 2 lb Bag` at 0.85. The shelf was widened to ten and the lemon resolves.
The first five results at this store are, quite literally, the ads.

**The recipe named its own stand-ins; the first build ignored them.** The real recipe
says "1/2 teaspoon dried herbs (such as herbes de provence or dried oregano)". The
first build stripped the parentheses and asked the store for `herbs` — a category, and
no shelf holds one; the best candidate scored 0.60 inside ten tiles and the line was
refused. But this recipe had *named its stand-ins*. The fix reads them: when a bare
category head carries a "(such as X or Y)" list, the first stand-in becomes the
purchase — the store answers `herbs de provence` with "Great Value Organic Herbs De
Provence, 0.6 oz" at 0.85. Nothing is invented: the words are the recipe's own. A line
that names no stand-in is still refused by name — a named hole beats a wrong item in a
cart.

**The store throttles.** A burst of searches earns an honest `429 Too Many Requests`.
The search now retries once after a short wait on exactly the store's "try later"
answers (429/503), then names the failure if it stands — a refusal for a real reason,
never a silent hole.

### 6.2 Evidence (live, 2026-09-29)

- Import of a real creator link (`skinnytaste.com/air-fryer-chicken-thighs`) → title,
  creator, 8 ingredients with amounts, confidence 0.95, from the page's own JSON-LD.
- The committed fixture run matches 8 of 8 lines; pointed at the app repo's profile
  (`MTC_ROOT=../meal-to-cart-app`) it renders a cart link with real usItemIds —
  `44391659` = "Fresh Lemons, 2 lb Bag", `676979470` = "Great Value Garlic Powder".
- The same real link run end-to-end through the wizard's agent: 200 OK; the pre-fix
  run matched 7 of 8 lines, the eighth the "herbs" refusal now fixed above.
- The stand-ins fix, live: `herbs de provence` resolves to "Great Value Organic Herbs
  De Provence, 0.6 oz" at 0.85; engine suite 85 passed / 1 skipped after the fix.
- Tests: engine green (1 skip: per-machine terms file), wizard app green (2 skips, same
  reason). `python -m meal_to_cart.guard` passes on both trees.

**The cart really fills.** The emitted link was opened for real in a headed Chrome on a
residential connection (fresh profile, no account). The addToCart URL ran with no
challenge, Walmart answered, and the cart reads **7 items, $32.31** — the recipe's
garlic powder, lemons, chicken thighs, onion powder, herbs de provence, sweet paprika
and black pepper, matched back against the live cart's own product records. The eighth
line, kosher salt, was refused by Walmart itself at add time — "out of stock, please
check back later" — named, not hidden: search-time availability is not add-time
availability, and the cart says so out loud. (From datacenter networks and headless
browsers the same URL meets Walmart's bot challenge first; from a normal browser it
does not.)

### 6.3 The store changes under you (live, 2026-09-30)

Three live failures, found by re-running the whole flow instead of trusting yesterday's
green. Each one was real, and none of them was in the matching logic.

**The price block moved, then emptied.** Overnight the store's search blob stopped
carrying per-tile prices at all — 0 of 109 tiles in a saved page had a price (`priceInfo`
present but empty) — and the field itself had moved from `currentPrice` to `itemPrice`.
Two bugs surfaced at once: the parser was reading the old field, and the wizard was
summing an empty priced set as `$0.00` — a free week. Fixed twice over: the parser reads
`currentPrice`, `itemPrice` or `linePrice` and returns nothing rather than zero, and the
wizard refuses to render a total over zero priced lines; it says out loud that prices
did not come back rather than guessing one. A total is a claim; a page that cannot make
it should not.

**The wall is not a header problem.** The same request shape that earned HTTP 412 from a
datacenter network came back as an intermittent 307 to `/blocked`: a velocity wall,
measured live at 4 walls in 5 attempts at 15s spacing and 3 passes in 3 at 25s. The fix
is honest pacing plus retries: `MTC_SEARCH_GAP` spaces searches, and a walled search is
retried up to 4 times before it is named as a refusal. During the recorded demo the
server's window locked hard, so the demo's store reads ran through the operator's own
browser on their own network — the machine that owns the store session, which is where
the product says the agent belongs anyway. (The shipped engine keeps its plain HTTP
client; the browser ride-along is two clearly-labelled demo files, not a product path.)

**The page gave up before the agent did.** The wizard's build timeout was 3 minutes; a
paced build takes longer than that by design. The page now waits 10 minutes and keeps
the working state visible, because a paced store means a slow build, not a failed one.

**The final take, end to end (2026-09-30):** real creator link imported; build paced at
5s through the store; `Built: 1 dinner, 8 list lines, nothing unresolved, a cart link.`
The emitted link opened in the operator's own browser; the cart reads **Cart (8 items),
$34.59** — all eight recipe lines, kosher salt included this time. Engine 93 passed / 1
skipped, wizard 33 passed / 2 skipped, both guards clean. The 55-second recording is app
page → filled cart, no narration — the voice belongs to the person demoing.
