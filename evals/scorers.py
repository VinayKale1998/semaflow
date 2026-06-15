"""Pure scoring functions for the Stage 6 governance scorecard.

Every function here takes labels and observed outputs and returns a CaseResult.
There is no I/O: no LLM, no DB, no YAML. The runners (Pieces 3-7) call these
after they have produced the observed values, so scoring stays deterministic and
unit-testable in isolation.

The governance framing shows up in two scorers:
  - score_measure treats (expected None, actual None) as a PASS: refusing to
    select a measure for an out-of-scope question is correct behavior.
  - score_hedge passes when the predicted hedge (confidence below the gate)
    matches whether the case was labeled as one that should hedge. Correctly
    hedging on an unanswerable question is a pass, not a failure.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from pydantic import BaseModel

CONFIDENCE_GATE = 0.7  # mirrors graph.CONFIDENCE_THRESHOLD


class CaseResult(BaseModel):
    """The scored outcome of one case on one dimension."""

    dimension: str
    case_id: str
    passed: bool
    expected: str
    actual: str
    detail: str = ""


# ── routing ──────────────────────────────────────────────────────────────────

def score_route(case_id: str, expected: str, actual: str) -> CaseResult:
    return CaseResult(
        dimension="routing",
        case_id=case_id,
        passed=expected == actual,
        expected=expected,
        actual=actual,
    )


# ── measure selection ────────────────────────────────────────────────────────

def score_measure(case_id: str, expected: str | None, actual: str | None) -> CaseResult:
    """A correct refusal (both None) is a pass. Selecting a measure when none was
    expected is a hallucination; selecting the wrong one is a miss."""
    passed = expected == actual
    if expected is None and actual is None:
        detail = "correct refusal (no measure for out-of-scope question)"
    elif expected is None and actual is not None:
        detail = f"hallucinated measure {actual!r} for out-of-scope question"
    elif actual is None:
        detail = f"refused but a measure was expected"
    else:
        detail = "" if passed else f"wrong measure"
    return CaseResult(
        dimension="measure_selection",
        case_id=case_id,
        passed=passed,
        expected=str(expected),
        actual=str(actual),
        detail=detail,
    )


def _glossary_leaves(refs: Iterable[str]) -> set[str]:
    """Normalize glossary refs to their leaf token (after the last dot).

    Robust to namespace-prefix drift between the dataset ('time_periods.last_quarter')
    and whatever the node emits ('last_quarter'). Safe here because every glossary
    leaf in semantic_layer.yaml is unique across namespaces.
    """
    return {r.rsplit(".", 1)[-1] for r in refs}


def score_glossary(case_id: str, expected: list[str], actual: list[str]) -> CaseResult:
    exp = _glossary_leaves(expected)
    act = _glossary_leaves(actual)
    passed = exp == act
    detail = ""
    if not passed:
        missing = exp - act
        extra = act - exp
        bits = []
        if missing:
            bits.append(f"missing {sorted(missing)}")
        if extra:
            bits.append(f"extra {sorted(extra)}")
        detail = "; ".join(bits)
    return CaseResult(
        dimension="glossary",
        case_id=case_id,
        passed=passed,
        expected=str(sorted(exp)),
        actual=str(sorted(act)),
        detail=detail,
    )


# ── pipeline status / trust boundary ─────────────────────────────────────────

def score_status(case_id: str, expected: str, actual: str) -> CaseResult:
    return CaseResult(
        dimension="pipeline_status",
        case_id=case_id,
        passed=expected == actual,
        expected=expected,
        actual=actual,
    )


# ── retrieval hit-rate ───────────────────────────────────────────────────────

class RetrievalScore(BaseModel):
    case_id: str
    hit: bool                 # any expected source present in the top-k retrieved
    rank: int | None          # 1-based rank of the first expected source, or None
    reciprocal_rank: float    # 1/rank, or 0.0 on a miss
    expected_sources: list[str]
    retrieved_sources: list[str]


def score_retrieval(
    case_id: str, expected_sources: list[str], retrieved_sources: list[str]
) -> RetrievalScore:
    """hit@k and reciprocal rank. retrieved_sources is the ranked list (top-k
    already applied by the caller). A case with no expected sources should not be
    scored here; callers filter those out."""
    expected = set(expected_sources)
    rank: int | None = None
    for i, src in enumerate(retrieved_sources, start=1):
        if src in expected:
            rank = i
            break
    return RetrievalScore(
        case_id=case_id,
        hit=rank is not None,
        rank=rank,
        reciprocal_rank=(1.0 / rank) if rank else 0.0,
        expected_sources=sorted(expected),
        retrieved_sources=retrieved_sources,
    )


# ── hedge calibration ────────────────────────────────────────────────────────

def score_hedge(
    case_id: str, expects_hedge: bool, confidence: float, gate: float = CONFIDENCE_GATE
) -> CaseResult:
    """The reviewer hedges (the confidence gate fires) when confidence < gate.
    The case passes when that prediction matches the label: a resolving case
    must clear the gate, an unanswerable case must fall below it."""
    predicted_hedge = confidence < gate
    passed = predicted_hedge == expects_hedge
    detail = f"confidence={confidence:.2f} gate={gate} predicted_hedge={predicted_hedge}"
    return CaseResult(
        dimension="hedge_calibration",
        case_id=case_id,
        passed=passed,
        expected=f"hedge={expects_hedge}",
        actual=f"hedge={predicted_hedge}",
        detail=detail,
    )


# ── guardrails ───────────────────────────────────────────────────────────────

def score_guardrail(
    case_id: str,
    target_layer: str,
    reason_fragments: list[str],
    *,
    passed_overall: bool,
    layer_booleans: dict[str, bool],
    violations: list[str],
) -> CaseResult:
    """A guardrail case passes only if ALL of these hold:
      - the overall verdict is rejection (passed_overall is False),
      - the targeted layer reported False,
      - every other layer reported True (isolation: a clean single-failure probe),
      - the violations name the right reason.
    Isolation is what makes the case a real probe of its target layer rather than
    a green test riding on an unrelated failure.
    """
    failures: list[str] = []
    if passed_overall:
        failures.append("guardrail did not reject")
    if layer_booleans.get(target_layer, True) is not False:
        failures.append(f"target layer {target_layer} did not fail")
    for layer, ok in layer_booleans.items():
        if layer != target_layer and ok is not True:
            failures.append(f"non-target layer {layer} also failed (not isolated)")
    blob = " ".join(violations)
    for frag in reason_fragments:
        if frag not in blob:
            failures.append(f"missing reason fragment {frag!r}")
    passed = not failures
    return CaseResult(
        dimension="guardrails",
        case_id=case_id,
        passed=passed,
        expected=f"reject@{target_layer}",
        actual="rejected" if not passed_overall else "passed",
        detail="" if passed else "; ".join(failures),
    )


# ── aggregation ──────────────────────────────────────────────────────────────

class DimensionSummary(BaseModel):
    dimension: str
    passed: int
    total: int

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


def summarize(results: Iterable[CaseResult]) -> dict[str, DimensionSummary]:
    """Roll per-case results up to per-dimension pass counts."""
    buckets: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        buckets[r.dimension].append(r)
    return {
        dim: DimensionSummary(
            dimension=dim,
            passed=sum(1 for r in rs if r.passed),
            total=len(rs),
        )
        for dim, rs in buckets.items()
    }


def retrieval_summary(scores: list[RetrievalScore]) -> dict[str, float]:
    """hit-rate and mean reciprocal rank over a set of retrieval scores."""
    if not scores:
        return {"hit_rate": 0.0, "mrr": 0.0, "n": 0}
    hits = sum(1 for s in scores if s.hit)
    mrr = sum(s.reciprocal_rank for s in scores) / len(scores)
    return {"hit_rate": hits / len(scores), "mrr": mrr, "n": len(scores)}
