"""The live probe is opt-in.

It spawns a browser and searches Walmart, which spends the request budget that the
agent needs for real runs -- and while the suite was running it on every invocation,
it was competing with the agent for that budget. A default test run is offline.
"""
import json
import os
import subprocess
import sys

import pytest

LIVE = os.environ.get("MEAL_TO_CART_LIVE") == "1"

REQUIRED_TOOLS = ("search", "add_to_cart", "view_cart", "status")


@pytest.mark.skipif(not LIVE, reason="set MEAL_TO_CART_LIVE=1 to start a browser and search")
def test_probe_reports_required_tools():
    out = subprocess.run(
        [sys.executable, "scripts/probe_mcp.py", "--json"],
        capture_output=True, text=True, timeout=600,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    for tool in REQUIRED_TOOLS:
        assert tool in payload["tools"], f"missing {tool}: {payload['tools']}"


def test_the_suite_is_offline_by_default():
    """Guard against someone re-arming the live probe by accident."""
    assert not LIVE or os.environ["MEAL_TO_CART_LIVE"] == "1"


def test_the_client_never_exposes_checkout():
    from meal_to_cart import walmart

    assert "checkout" in walmart.NEVER_CALLED
    assert "checkout" not in walmart.ALLOWED_TOOLS
    assert not hasattr(walmart.WalmartMCP, "checkout")
    assert not hasattr(walmart.WalmartMCP, "pay")


def test_no_source_line_can_call_checkout():
    """There is no code path that pays: the call has to be written somewhere."""
    import pathlib

    offenders = []
    for path in pathlib.Path("src").rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            code = line.split("#", 1)[0]
            if "checkout" in code and "NEVER_CALLED" not in code:
                offenders.append(f"{path}:{number}")
    assert offenders == [], offenders
