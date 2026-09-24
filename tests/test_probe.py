import json
import subprocess
import sys


def test_probe_reports_required_tools():
    """The probe must prove the server exposes the four tools the agent needs."""
    out = subprocess.run(
        [sys.executable, "scripts/probe_mcp.py", "--json"],
        capture_output=True, text=True, timeout=600,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    for tool in ("search", "add_to_cart", "view_cart", "status"):
        assert tool in payload["tools"], f"missing {tool}: {payload['tools']}"
