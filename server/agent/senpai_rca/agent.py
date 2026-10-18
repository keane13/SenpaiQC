"""`adk web agent/` entry point for local debugging of the root-cause agent.

Binds the tools to the most recent open investigation in the configured backend.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server" / "api"))

from adapters.adk_agent import build_agent  # noqa: E402
from config import get_settings  # noqa: E402
from container import get_container  # noqa: E402
from slices.learn.rca_tools import RcaToolbox  # noqa: E402

_c = get_container()
_open = [i for i in _c.docs.list("investigations", 50) if i["status"] == "open"]
if not _open:
    raise RuntimeError("no open investigation: run POST /api/learn/scan first")
root_agent = build_agent(RcaToolbox(_c.events, _c.cards, _open[0]), get_settings().text_model)
