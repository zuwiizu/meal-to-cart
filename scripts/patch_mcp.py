#!/usr/bin/env python3
"""Two measured fixes for @striderlabs/mcp-walmart@0.2.1.

BUG 1 - the User-Agent lies about the browser
---------------------------------------------
`dist/browser.js` announces Chrome/120.0.0.0 while the package ships
patchright 1.63.0, whose bundled Chromium is 153. Walmart's bot detection
answers the mismatch with a "Robot or human?" CAPTCHA. Measured on one
machine, same minute, only the User-Agent varied:

    Chrome/120.0.0.0  ->  0 product cards   title "Robot or human?"
    Chrome/131.0.0.0  ->  0 product cards   title "Robot or human?"
    Chrome/153.0.0.0  -> 21 product cards   title "feta cheese - Walmart.com"

The launch flags and the injected stealth script made no difference; the
version string alone decided it.

BUG 2 - a block page poisons the session forever
------------------------------------------------
On a blocked page the server still saves cookies. Those cookies carry the
PerimeterX block fingerprint (_pxvid, pxcts, btc, bsc, btc, vtc), and every
later run reloads them, so one block becomes permanent. Measured:

    poisoned cookie jar  -> every search returns /blocked?uuid=...
    rm cookies.json      -> the next search returns 3 real products

The fix here is diagnostic only: name the block for what it is, so the agent
can reset instead of reporting a vague "no products found". The reset itself
lives in src/meal_to_cart/walmart.py.

Both patches are idempotent and fail loudly if upstream changes the strings.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = (ROOT / "vendor" / "walmart-mcp" / "node_modules" / "@striderlabs"
        / "mcp-walmart" / "dist")
BROWSER_JS = DIST / "browser.js"
INDEX_JS = DIST / "index.js"
BROWSERS = ROOT / ".cache" / "ms-playwright"

UA_PATTERN = re.compile(r"Chrome/\d+\.0\.0\.0")
VERSION_PATTERN = re.compile(r"(\d+)\.\d+\.\d+")

ORIGINAL_CATCH = '''        catch {
            return err("No products found or page failed to load");
        }'''

# The sentence the agent keys on when deciding to reset a poisoned session.
BLOCK_MARKER = "BLOCKED_BY_WALMART"

PATCHED_CATCH = '''        catch (e) {
            try {
                const t = await page.title();
                if (t && t.indexOf("Robot or human") !== -1) {
                    console.error("[meal-to-cart] Walmart bot wall at " + page.url());
                    return err("''' + BLOCK_MARKER + ''' Walmart returned its bot-detection page");
                }
            } catch (inner) { /* fall through to the generic message */ }
            return err("No products found or page failed to load");
        }'''


def bundled_chrome_major() -> str:
    shells = sorted(BROWSERS.glob("chromium*/**/chrome-headless-shell"))
    if not shells:
        raise SystemExit("no bundled Chromium under .cache/ms-playwright "
                         "-- run scripts/setup_mcp.sh first")
    for shell in shells:
        try:
            done = subprocess.run([str(shell), "--version"],
                                  capture_output=True, text=True, timeout=60)
        except OSError:
            continue
        match = VERSION_PATTERN.search(done.stdout or done.stderr)
        if match:
            return match.group(1)
    raise SystemExit("could not read a version out of the bundled Chromium")


def fix_user_agent() -> str:
    if not BROWSER_JS.exists():
        raise SystemExit(f"not installed: {BROWSER_JS}\nrun scripts/setup_mcp.sh first")
    want = f"Chrome/{bundled_chrome_major()}.0.0.0"
    text = BROWSER_JS.read_text()
    found = UA_PATTERN.findall(text)
    if not found:
        raise SystemExit("no Chrome/x.0.0.0 User-Agent in browser.js -- upstream "
                         "changed the string; re-read the file before trusting this")
    if all(f == want for f in found):
        return f"user-agent already {want}"
    BROWSER_JS.write_text(UA_PATTERN.sub(want, text))
    return f"user-agent {', '.join(sorted(set(found)))} -> {want}"


def fix_block_reporting() -> str:
    text = INDEX_JS.read_text()
    if BLOCK_MARKER in text:
        return "block reporting already patched"
    if ORIGINAL_CATCH not in text:
        raise SystemExit("the search catch block in index.js is not the expected "
                         "shape -- upstream changed it; re-read before patching")
    INDEX_JS.write_text(text.replace(ORIGINAL_CATCH, PATCHED_CATCH, 1))
    return "block reporting patched (bot wall now names itself)"


def main() -> int:
    print("patch 1:", fix_user_agent())
    print("patch 2:", fix_block_reporting())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
