"""Turn a weekly meal plan into a reviewed Walmart cart.

The engine is deliberately two halves with one seam between them. The
household's side (importer, mealplan, aggregate) turns recipes into a week
and a week into lines on a list. The store's side (walmart, match, cart,
gateway) turns lines into products. resolve.py is the seam: a planned line
becomes either a product or a NAMED refusal, and a cart link is only ever
rendered when nothing is left unnamed.

Two callers share it, and they are the reason for the shape:

    the app repo    the wizard a visitor drives (meal_to_cart_app.agent)
    cli.py          the household's own run, no browser

Nothing here reads the household's files at import time: the profile root
comes from MTC_ROOT when a caller relocates it (the app does, to its own
repo), and a reader with no profile yet simply reads nothing.
"""
