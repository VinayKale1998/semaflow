"""Shared result envelope for the dimension runners.

Each runner (Pieces 3-7) produces a list of per-case dicts plus a summary dict,
and writes them under evals/results/<dimension>.json. Piece 8 reads these back to
assemble the scorecard, so the runners can be run independently and at different
times (the expensive LLM dimensions need not re-run to regenerate the report).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"


def save_results(
    dimension: str,
    summary: dict[str, Any],
    cases: list[dict[str, Any]],
    results_dir: Path | None = None,
) -> Path:
    results_dir = results_dir or RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dimension": dimension,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "cases": cases,
    }
    path = results_dir / f"{dimension}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_results(dimension: str, results_dir: Path | None = None) -> dict[str, Any] | None:
    results_dir = results_dir or RESULTS_DIR
    path = results_dir / f"{dimension}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
