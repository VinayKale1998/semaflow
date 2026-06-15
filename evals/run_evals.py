"""Stage 6 eval entry point.

Run one or more governance dimensions and regenerate the scorecard. Each runner
writes evals/results/<dimension>.json; report.py reads those back, so dimensions
can be run at different times and the scorecard reassembled without rerunning the
expensive LLM passes.

Usage (from project root, venv active, DB up for retrieval/hedge):
  python -m evals.run_evals --all              # run every dimension, then report
  python -m evals.run_evals guardrails routing # run a subset, then report
  python -m evals.run_evals --report           # only rebuild scorecard.md from JSONs

Dimensions and their cost:
  guardrails         offline (no LLM, no DB)
  routing            LLM (Haiku), no DB
  measure_selection  LLM (Haiku), no DB
  retrieval          local models, needs DB (pgvector)
  hedge              LLM (full orchestrator), needs DB  [most expensive]
"""
from __future__ import annotations

import argparse
import logging

from evals.report import write_scorecard
from evals.results_io import save_results
from evals.runners import guardrails, hedge, measure_selection, retrieval, routing

logger = logging.getLogger(__name__)

# name -> (module, results-file dimension key)
_RUNNERS = {
    "guardrails": (guardrails, "guardrails"),
    "routing": (routing, "routing"),
    "measure_selection": (measure_selection, "measure_selection"),
    "retrieval": (retrieval, "retrieval"),
    "hedge": (hedge, "hedge_calibration"),
}


def _run_one(name: str) -> None:
    module, dim_key = _RUNNERS[name]
    print(f"\n=== running {name} ===")
    summary, cases = module.run()
    save_results(dim_key, summary, cases)
    print(f"  saved {dim_key} ({summary.get('passed', '?')}/{summary.get('total', '?')})")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    parser = argparse.ArgumentParser(description="SemaFlow Stage 6 governance evals")
    parser.add_argument("dimensions", nargs="*", choices=list(_RUNNERS),
                        help="dimensions to run (default: none; use --all)")
    parser.add_argument("--all", action="store_true", help="run every dimension")
    parser.add_argument("--report", action="store_true",
                        help="rebuild scorecard.md from existing result JSONs only")
    args = parser.parse_args()

    to_run = list(_RUNNERS) if args.all else list(args.dimensions)
    for name in to_run:
        _run_one(name)

    if to_run or args.report:
        path = write_scorecard()
        print(f"\nScorecard written to {path}")
    elif not args.report:
        parser.print_help()


if __name__ == "__main__":
    main()
