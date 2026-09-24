# Build prompts

The prompts that produced the code, in order, with what each one was for.

## 1. Spec first

```
/writing-plans  — write the implementation plan against the PRD, task by task, with real
code in every step. No placeholders. Every task ends with a command whose output I can
check. Put the riskiest third-party dependency in Task 1 so it fails early if it is going
to fail.
```

## 2. De-risk the unknown before building on it

```
Write a probe that starts the Walmart MCP server over stdio, lists its tools, and calls
status. Prove the four tools we need exist before a single line of matching code is
written. If it does not work, say so and stop — do not proceed on an unverified
dependency.
```

## 3. Ground the data model in the real output

```
Do not assume the shape of the pipeline's Buy object. Go and read it, then use the real
field names. Same for the shopping list: print every line and write the normaliser against
the lines that actually exist, not against examples you invented.
```

## 4. Debug by elimination, not by guessing

```
The MCP returns "no products found" but a plain Playwright script against the same URL
returns 21 product cards. Bisect the difference: launch flags, viewport, context options,
user agent, stealth script. Change one thing at a time and report the card count for each.
```

## 5. Make the fix reproducible

```
Turn the fix into a script that re-derives the value from the installed browser and is
idempotent, and that fails loudly if upstream changes the string it patches. A hardcoded
constant would break silently on the next upgrade.
```

## 6. Prove the gate, not just the feature

```
Write the tests that assert the things that must NEVER happen: a flagged item is never
added, an item with no id is never added, a dry run never touches the gateway, a
non-interactive run never treats silence as consent.
```

## 7. Privacy as a build gate

```
The privacy rule must be enforced by the build, not by remembering. Write a guard that
scans every published file for the banned terms and exits non-zero, and wire it into the
release check.
```
