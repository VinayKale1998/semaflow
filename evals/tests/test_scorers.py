"""Pure unit tests for the eval scorers and dataset loader.

No LLM, no DB. These pin the scoring contract the runners depend on, including
the two governance-specific rules: a correct refusal (measure None==None) is a
pass, and a correctly-predicted hedge is a pass.
"""
from evals.loader import load_adversarial_set, load_eval_cases
from evals.scorers import (
    retrieval_summary,
    score_glossary,
    score_guardrail,
    score_hedge,
    score_measure,
    score_retrieval,
    score_route,
    score_status,
    summarize,
)


# ── dataset loads and self-consistency ───────────────────────────────────────

def test_eval_dataset_loads_and_is_consistent():
    cases = load_eval_cases()
    assert len(cases) == 36
    for c in cases:
        if c.category in ("sql_positive", "hybrid_positive"):
            assert c.expected_measure, c.id
        if c.category == "sql_oos":
            assert c.expected_measure is None and c.expected_status == "no_measure_matched"
        if c.category in ("rag_positive", "hybrid_positive"):
            assert c.expected_sources, c.id
        if c.category == "rag_oos":
            assert c.expects_hedge is True, c.id


def test_adversarial_dataset_loads():
    aset = load_adversarial_set()
    assert aset.max_rows == 1000
    assert len(aset.cases) == 7
    assert {c.fails for c in aset.cases} <= {
        "is_read_only", "schema_valid", "joins_safe", "row_limit_enforced"
    }


# ── routing ──────────────────────────────────────────────────────────────────

def test_score_route():
    assert score_route("c", "sql", "sql").passed
    assert not score_route("c", "sql", "hybrid").passed


# ── measure selection (governance) ───────────────────────────────────────────

def test_score_measure_correct_pick():
    assert score_measure("c", "aov_by_state", "aov_by_state").passed


def test_score_measure_correct_refusal_is_a_pass():
    r = score_measure("c", None, None)
    assert r.passed
    assert "refusal" in r.detail


def test_score_measure_hallucination_is_a_fail():
    r = score_measure("c", None, "aov_by_state")
    assert not r.passed
    assert "hallucinated" in r.detail


def test_score_measure_wrong_pick_fails():
    assert not score_measure("c", "aov_by_state", "top_categories_by_revenue").passed


# ── glossary (namespace-insensitive leaf comparison) ─────────────────────────

def test_score_glossary_leaf_normalization():
    assert score_glossary("c", ["time_periods.last_quarter"], ["last_quarter"]).passed
    assert score_glossary(
        "c", ["regions.south", "time_periods.last_month"], ["last_month", "south"]
    ).passed


def test_score_glossary_reports_missing_and_extra():
    r = score_glossary("c", ["regions.south"], ["regions.north"])
    assert not r.passed
    assert "missing" in r.detail and "extra" in r.detail


# ── pipeline status ──────────────────────────────────────────────────────────

def test_score_status():
    assert score_status("c", "success", "success").passed
    assert not score_status("c", "no_measure_matched", "success").passed


# ── retrieval ────────────────────────────────────────────────────────────────

def test_score_retrieval_hit_and_rank():
    s = score_retrieval("c", ["fact_orders.md"], ["dim_customers.md", "fact_orders.md"])
    assert s.hit and s.rank == 2 and s.reciprocal_rank == 0.5


def test_score_retrieval_miss():
    s = score_retrieval("c", ["fact_orders.md"], ["dim_customers.md"])
    assert not s.hit and s.rank is None and s.reciprocal_rank == 0.0


def test_score_retrieval_any_of_expected():
    # any-of: either expected source counts as a hit
    s = score_retrieval("c", ["a.md", "b.md"], ["x.md", "b.md"])
    assert s.hit and s.rank == 2


def test_retrieval_summary():
    scores = [
        score_retrieval("a", ["x.md"], ["x.md"]),          # rank 1, rr 1.0
        score_retrieval("b", ["y.md"], ["z.md", "y.md"]),  # rank 2, rr 0.5
        score_retrieval("c", ["w.md"], ["q.md"]),          # miss
    ]
    summ = retrieval_summary(scores)
    assert summ["n"] == 3
    assert abs(summ["hit_rate"] - 2 / 3) < 1e-9
    assert abs(summ["mrr"] - (1.0 + 0.5 + 0.0) / 3) < 1e-9


# ── hedge calibration (governance) ───────────────────────────────────────────

def test_score_hedge_resolving_case_must_clear_gate():
    assert score_hedge("c", expects_hedge=False, confidence=0.95).passed
    assert not score_hedge("c", expects_hedge=False, confidence=0.30).passed


def test_score_hedge_unanswerable_case_must_fall_below_gate():
    assert score_hedge("c", expects_hedge=True, confidence=0.25).passed
    assert not score_hedge("c", expects_hedge=True, confidence=0.85).passed


def test_score_hedge_boundary_at_gate():
    # confidence exactly at the gate is NOT a hedge (gate is < not <=)
    assert score_hedge("c", expects_hedge=False, confidence=0.70).passed


# ── guardrails ───────────────────────────────────────────────────────────────

def _layers(read=True, schema=True, joins=True, limit=True):
    return {
        "is_read_only": read,
        "schema_valid": schema,
        "joins_safe": joins,
        "row_limit_enforced": limit,
    }


def test_score_guardrail_clean_isolated_rejection_passes():
    r = score_guardrail(
        "c", "joins_safe", ["Forbidden join detected"],
        passed_overall=False,
        layer_booleans=_layers(joins=False),
        violations=["Forbidden join detected: fact_order_items -> fact_order_payments"],
    )
    assert r.passed, r.detail


def test_score_guardrail_not_rejecting_fails():
    r = score_guardrail(
        "c", "joins_safe", [],
        passed_overall=True,
        layer_booleans=_layers(),
        violations=[],
    )
    assert not r.passed and "did not reject" in r.detail


def test_score_guardrail_non_isolated_fails():
    # target layer failed but another also tripped -> not a clean probe
    r = score_guardrail(
        "c", "joins_safe", ["Forbidden join detected"],
        passed_overall=False,
        layer_booleans=_layers(joins=False, limit=False),
        violations=["Forbidden join detected", "No LIMIT clause"],
    )
    assert not r.passed and "not isolated" in r.detail


def test_score_guardrail_missing_reason_fragment_fails():
    r = score_guardrail(
        "c", "joins_safe", ["this fragment is absent"],
        passed_overall=False,
        layer_booleans=_layers(joins=False),
        violations=["Forbidden join detected"],
    )
    assert not r.passed and "missing reason fragment" in r.detail


# ── aggregation ──────────────────────────────────────────────────────────────

def test_summarize_counts_by_dimension():
    results = [
        score_route("a", "sql", "sql"),
        score_route("b", "sql", "rag"),
        score_status("c", "success", "success"),
    ]
    summ = summarize(results)
    assert summ["routing"].passed == 1 and summ["routing"].total == 2
    assert abs(summ["routing"].accuracy - 0.5) < 1e-9
    assert summ["pipeline_status"].passed == 1 and summ["pipeline_status"].total == 1
