"""Assemble the governance scorecard from the per-dimension result JSONs.

Reads evals/results/<dimension>.json (written by the runners) and renders
evals/results/scorecard.md: a one-table summary plus a short section per
dimension. Pure formatting, no LLM or DB, so the scorecard can be regenerated
any time without re-running the expensive dimensions.
"""
from __future__ import annotations

from pathlib import Path

from evals.results_io import RESULTS_DIR, load_results

_DIMENSIONS = ["routing", "measure_selection", "guardrails", "retrieval", "hedge_calibration"]


def _pct(passed: int, total: int) -> str:
    return f"{passed}/{total} ({passed / total:.0%})" if total else "n/a"


def _summary_rows() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []

    r = load_results("routing")
    if r:
        s = r["summary"]
        rows.append(("Routing accuracy", _pct(s["passed"], s["total"]),
                     f"out-of-scope {_pct(s['by_scope']['out_of_scope']['passed'], s['by_scope']['out_of_scope']['total'])}"))

    m = load_results("measure_selection")
    if m:
        s = m["summary"]
        ms, ps, gl = s["measure_selection"], s["pipeline_status"], s.get("glossary")
        rows.append(("Measure selection", _pct(ms["passed"], ms["total"]),
                     f"{s['refusals_via_gate']} refused via confidence gate"))
        rows.append(("Trust boundary (refuse/proceed)", _pct(ps["passed"], ps["total"]),
                     f"gate threshold {s['gate_threshold']}"))
        if gl:
            rows.append(("Glossary resolution", _pct(gl["passed"], gl["total"]), ""))

    g = load_results("guardrails")
    if g:
        s = g["summary"]
        rows.append(("Guardrail efficacy", _pct(s["passed"], s["total"]),
                     "every layer isolated"))

    rt = load_results("retrieval")
    if rt:
        s = rt["summary"]
        rows.append((f"Retrieval hit@{s['top_k']}", _pct(s["passed"], s["total"]),
                     f"MRR {s['mrr']:.3f}"))

    h = load_results("hedge_calibration")
    if h:
        s = h["summary"]
        rows.append(("Hedge calibration", _pct(s["passed"], s["total"]),
                     f"resolving {_pct(s['resolving_pass'], s['resolving_total'])}, "
                     f"hedge {_pct(s['hedge_pass'], s['hedge_total'])}"))
    return rows


def _routing_section(lines: list[str]) -> None:
    r = load_results("routing")
    if not r:
        return
    s = r["summary"]
    routes = ["sql", "rag", "hybrid"]
    lines += ["## Routing", "",
              "Classifies a question by SHAPE. Out-of-scope questions are still "
              "routed correctly even though the system will later refuse or hedge.", "",
              "Confusion matrix (rows = expected, cols = actual):", "",
              "| expected \\ actual | " + " | ".join(routes) + " |",
              "|" + "---|" * (len(routes) + 1)]
    for e in routes:
        lines.append(f"| {e} | " + " | ".join(str(s["confusion"][e][a]) for a in routes) + " |")
    fails = [c for c in r["cases"] if not c["passed"]]
    if fails:
        lines += ["", "Misses:"]
        lines += [f"- `{c['case_id']}` ({c['category']}): expected {c['expected']}, "
                  f"got {c['actual']} (conf {c['route_confidence']:.2f})" for c in fails]
    lines.append("")


def _measure_section(lines: list[str]) -> None:
    m = load_results("measure_selection")
    if not m:
        return
    s = m["summary"]
    lines += ["## Measure selection and the SQL trust boundary", "",
              f"The node selects a governed measure; a selection below the "
              f"{s['gate_threshold']} confidence gate becomes an honest "
              f"`no_measure_matched` refusal. {s['refusals_via_gate']} out-of-scope "
              f"question(s) were refused via the gate (the rest by the node directly).", ""]
    fails = [c for c in m["cases"] if not (c["measure_passed"] and c["status_passed"]
                                           and c.get("glossary_passed", True))]
    if fails:
        lines += ["Misses:"]
        for c in fails:
            lines.append(f"- `{c['case_id']}` ({c['category']}): expected "
                         f"{c['expected_measure']}, got {c['selected_measure']}")
    else:
        lines.append("All measure, status, and glossary checks passed.")
    lines.append("")


def _guardrail_section(lines: list[str]) -> None:
    g = load_results("guardrails")
    if not g:
        return
    s = g["summary"]
    lines += ["## Guardrails", "",
              "Each adversarial SQL must be rejected by exactly one layer, in "
              "isolation (the other three pass).", "",
              "| layer | caught |", "|---|---|"]
    for layer, b in s["by_layer"].items():
        lines.append(f"| {layer} | {_pct(b['passed'], b['total'])} |")
    lines.append("")


def _retrieval_section(lines: list[str]) -> None:
    rt = load_results("retrieval")
    if not rt:
        return
    s = rt["summary"]
    lines += ["## Retrieval", "",
              f"Hybrid retrieval (pgvector + BM25, RRF, cross-encoder rerank). "
              f"hit@{s['top_k']} = {_pct(s['passed'], s['total'])}, MRR = {s['mrr']:.3f}.", ""]
    misses = [c for c in rt["cases"] if not c["passed"]]
    if misses:
        lines += ["Misses:"]
        lines += [f"- `{c['case_id']}`: expected {c['expected_sources']}, "
                  f"got {c['retrieved_sources']}" for c in misses]
        lines.append("")


def _hedge_section(lines: list[str]) -> None:
    h = load_results("hedge_calibration")
    if not h:
        return
    s = h["summary"]
    lines += ["## Hedge calibration", "",
              f"Confidence gate = {s['gate']}. Resolving questions must clear it; "
              f"unanswerable questions must trip it (the loop fires and, finding no "
              f"better source, terminates with an honest hedge).", "",
              "| case | category | expects hedge | confidence | revisions | result |",
              "|---|---|---|---|---|---|"]
    for c in h["cases"]:
        lines.append(f"| {c['case_id']} | {c['category']} | {c['expects_hedge']} | "
                     f"{c['confidence']:.2f} | {c['revision_count']} | "
                     f"{'PASS' if c['passed'] else 'FAIL'} |")
    lines.append("")


def build_scorecard() -> str:
    any_dim = next((load_results(d) for d in _DIMENSIONS if load_results(d)), None)
    ts = any_dim["timestamp"] if any_dim else "n/a"

    lines = [
        "# SemaFlow Governance Scorecard",
        "",
        f"Generated from the latest dimension runs (most recent: {ts}). The LLM "
        "dimensions (routing, measure selection, hedge) use Claude Haiku and are "
        "nondeterministic; expect movement of about one case across runs.",
        "",
        "This is a governance scorecard, not an answer-quality benchmark. It scores "
        "whether the system routes correctly, selects only governed measures, "
        "refuses out-of-scope questions, blocks unsafe SQL, retrieves the right "
        "document, and hedges when the corpus cannot answer.",
        "",
        "## Summary",
        "",
        "| Dimension | Score | Notes |",
        "|---|---|---|",
    ]
    for name, score, note in _summary_rows():
        lines.append(f"| {name} | {score} | {note} |")
    lines.append("")

    _routing_section(lines)
    _measure_section(lines)
    _guardrail_section(lines)
    _retrieval_section(lines)
    _hedge_section(lines)
    return "\n".join(lines)


def write_scorecard(path: Path | None = None) -> Path:
    path = path or (RESULTS_DIR / "scorecard.md")
    path.write_text(build_scorecard(), encoding="utf-8")
    return path


if __name__ == "__main__":
    p = write_scorecard()
    print(f"wrote {p}")
