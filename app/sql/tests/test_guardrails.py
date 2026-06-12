"""Guardrail negative-path tests.

The guardrail runs four independent checks (read-only, schema allow-list, join
safety, row limit) and does NOT short-circuit: every check runs, so the result
carries a per-layer boolean plus a flat list of violation reasons. test_pipeline.py
covers the happy path; this file covers each rejection path by injecting a SQL
crafted to fail exactly one layer.

Isolation is the point. Each injected SQL is built so only its target check can
fail and the other three pass. That makes every case a clean probe: a green test
proves the guardrail rejected for the intended reason, not because some unrelated
check happened to trip. Without it, a test could stay green while the check it
names silently rots (e.g. fan-out joins slip through but the row-limit check
fails instead, so `passed` is still False).
"""

import pytest

from app.sql.guardrails import run as run_guardrails
from app.sql.models import ResolvedSQL, SQLRequest

# Every per-layer boolean on GuardrailResult. Used to assert isolation: for each
# case, exactly one of these is False and the rest are True.
_CHECKS = ("is_read_only", "schema_valid", "joins_safe", "row_limit_enforced")

# (sql, layer_that_must_fail, reason_fragments_in_violations, max_rows)
_CASES = [
    pytest.param(
        "SELECT SUM(oi.price) AS revenue "
        "FROM fact_order_items oi "
        "JOIN fact_order_payments pay ON oi.order_id = pay.order_id "
        "LIMIT 1000",
        "joins_safe",
        ["Forbidden join detected", "fact_order_items -> fact_order_payments"],
        1000,
        id="forbidden_join_fans_out_revenue",
    ),
    pytest.param(
        # _check_schema only inspects FROM/JOIN, so UPDATE leaves schema_valid
        # True; LIMIT keeps the row-limit check happy. Only read-only fails.
        "UPDATE fact_orders SET order_status = 'shipped' LIMIT 5",
        "is_read_only",
        ["Write operation not allowed", "UPDATE"],
        1000,
        id="write_operation_blocked",
    ),
    pytest.param(
        "SELECT * FROM ghost_table LIMIT 10",
        "schema_valid",
        ["Unknown table referenced", "ghost_table"],
        1000,
        id="unknown_table_blocked",
    ),
    pytest.param(
        "SELECT order_id FROM fact_orders",
        "row_limit_enforced",
        ["No LIMIT clause"],
        1000,
        id="missing_limit_blocked",
    ),
    pytest.param(
        # LIMIT present but above max_rows=1000. A different failure mode of the
        # same check than missing_limit, so both are worth pinning.
        "SELECT order_id FROM fact_orders LIMIT 99999",
        "row_limit_enforced",
        ["exceeds max_rows"],
        1000,
        id="limit_exceeds_max_blocked",
    ),
]


@pytest.mark.parametrize("sql,fails,reason_fragments,max_rows", _CASES)
def test_guardrail_rejects(
    sql: str, fails: str, reason_fragments: list[str], max_rows: int
) -> None:
    # Hand-built ResolvedSQL: this tests the guardrail directly, not the LLM or
    # resolver. measure is a valid key but irrelevant to these checks.
    resolved = ResolvedSQL(
        sql=sql, measure="top_categories_by_revenue", parameters_applied={}
    )

    result = run_guardrails(resolved, SQLRequest(question="injected", max_rows=max_rows))

    # The overall verdict must be rejection.
    assert result.passed is False

    # The targeted layer is the one that failed.
    assert getattr(result, fails) is False, (
        f"expected {fails} to fail, got {result!r}"
    )

    # Every other layer passed, so this SQL is an isolated single-failure probe.
    for check in _CHECKS:
        if check == fails:
            continue
        assert getattr(result, check) is True, (
            f"{check} also failed; injection is not isolated: {result.violations!r}"
        )

    # The rejection is for the right reason, named explicitly in the violations.
    blob = " ".join(result.violations)
    for fragment in reason_fragments:
        assert fragment in blob, (
            f"missing {fragment!r} in violations {result.violations!r}"
        )
