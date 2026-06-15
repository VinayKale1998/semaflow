"""
Stage 3 pipeline facade.

Composes the four Stage 3 steps into one call so callers (the Stage 5
orchestrator, tests, the eventual API) do not have to wire them up:

    question -> node.run (measure selection)
             -> resolver.resolve (SQL assembly)
             -> guardrails.run (validation)
             -> executor.execute (run against Postgres)

Every failure mode is reported as a status on PipelineResult rather than
raised, so the orchestrator can branch on the outcome without try/except.
"""
import logging
from typing import Literal

from pydantic import BaseModel

from .executor import ExecutorError, execute
from .guardrails import run as guardrail_run
from .models import SQLRequest, SQLResponse
from .node import run as node_run
from .resolver import ResolverError, resolve

logger = logging.getLogger(__name__)

# Refuse a measure selection below this confidence. The node prompt instructs the
# model to pick the closest measure even when none fits well (prompts.py rule 3),
# so an out-of-scope question can select a wrong measure at low confidence and
# still resolve, pass guardrails, and execute, returning wrong-but-valid rows.
# This gate converts a low-confidence selection into an honest no_measure_matched
# refusal: the SQL half of the trust boundary. Added in Stage 6 after the eval
# (evals/runners/measure_selection.py) showed in-scope questions score ~0.95 and
# out-of-scope ~0.15, a clean separation. Mirrors the reviewer's 0.7 gate in
# graph.py. Tunable; static for now.
MEASURE_CONFIDENCE_THRESHOLD = 0.5


class PipelineResult(BaseModel):
    status: Literal[
        "success",
        "no_measure_matched",
        "resolution_failed",
        "guardrail_violation",
        "execution_failed",
    ]
    response: SQLResponse | None = None
    failure_reason: str | None = None
    failure_detail: dict | None = None


async def run_sql_pipeline(question: str) -> PipelineResult:
    """Full Stage 3 pipeline. Returns a PipelineResult tagged with status."""
    request = SQLRequest(question=question)

    selection = await node_run(request)
    if selection is None:
        logger.info("pipeline: no measure matched for question=%r", question)
        return PipelineResult(
            status="no_measure_matched",
            failure_reason="The model could not select a declared measure for this question.",
        )

    if selection.confidence < MEASURE_CONFIDENCE_THRESHOLD:
        logger.info(
            "pipeline: measure %s selected at low confidence %.2f (< %.2f), refusing; question=%r",
            selection.measure, selection.confidence, MEASURE_CONFIDENCE_THRESHOLD, question,
        )
        return PipelineResult(
            status="no_measure_matched",
            failure_reason=(
                f"Closest measure {selection.measure!r} was selected at confidence "
                f"{selection.confidence:.2f}, below the {MEASURE_CONFIDENCE_THRESHOLD} "
                "threshold. The question likely falls outside the governed measures."
            ),
            failure_detail={
                "rejected_measure": selection.measure,
                "confidence": selection.confidence,
            },
        )

    try:
        resolved = resolve(selection)
    except ResolverError as exc:
        logger.warning("pipeline: resolution failed: %s", exc)
        return PipelineResult(status="resolution_failed", failure_reason=str(exc))

    guardrail = guardrail_run(resolved, request)
    if not guardrail.passed:
        logger.warning("pipeline: guardrail violations: %s", guardrail.violations)
        return PipelineResult(
            status="guardrail_violation",
            failure_reason="Resolved SQL failed guardrail checks.",
            failure_detail={"violations": guardrail.violations},
        )

    try:
        response = execute(resolved)
    except ExecutorError as exc:
        logger.warning("pipeline: execution failed: %s", exc)
        return PipelineResult(status="execution_failed", failure_reason=str(exc))

    # Enrich the response with the upstream context the executor did not have.
    response.request = request
    response.model_selection = selection
    response.guardrail = guardrail

    logger.info(
        "pipeline: success measure=%s rows=%d", selection.measure, response.row_count
    )
    return PipelineResult(status="success", response=response)
