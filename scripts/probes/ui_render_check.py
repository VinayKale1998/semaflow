"""Drive the Streamlit UI through AppTest to confirm it renders without
exceptions on the two riskiest branches: the SQL bar-chart path and the hedge
revision-badge path. Uses the real orchestrator (cached once across reruns).

    .venv/bin/python scripts/probes/ui_render_check.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
load_dotenv(str(root / ".env"))

APP = str(root / "app" / "ui" / "streamlit_app.py")


def drive(query: str) -> None:
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    at.session_state["query"] = query
    # Submit is the last button (after the 4 sample buttons).
    at.button[len(at.button) - 1].click().run()
    excs = [e.value for e in at.exception]
    badges = [m.value for m in at.markdown if "badge" in m.value]
    print(f"\nQUERY: {query}")
    print(f"  exceptions: {excs}")
    print(f"  badges rendered: {badges}")
    if excs:
        raise SystemExit(f"UI raised exceptions: {excs}")


drive("Show me the top 5 product categories by revenue")
drive("How are damaged items handled when the seller is at fault?")
print("\nUI render check OK: no exceptions on either branch.")
