"""
Stage 5, Piece 4: Reviewer node.

Scores whether the synthesized answer is grounded in the sources that
produced it (SQL rows and/or retrieved chunks). The orchestrator uses the
score to decide whether to accept the answer or loop back once for a
revised retrieval pass.

Mirrors router.py: a Reviewer class with a single entry point, Claude Haiku
via forced tool use so the model can only return structured JSON, wrapped
with maybe_trace so the LLM call lands as a child span in LangSmith.

The reviewer judges, it does not retrieve or synthesize. The revised_query
it proposes is a suggestion; the revision retrieval node in graph.py decides
what to do with it. One revision maximum is enforced there, not here.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.llm.tracing import maybe_trace

if TYPE_CHECKING:
    from app.orchestrator.graph import OrchestratorState

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024

_SYSTEM_PROMPT = """\
You are the groundedness reviewer for a governed analytics system over the
Olist Brazilian e-commerce dataset. You are given a user question, an answer
that another model synthesized, and the exact sources that answer was meant
to be built from: SQL rows and/or retrieved document chunks.

You report two separate judgments.

grounded: whether every factual claim in the answer traces to a source: a
number or category present in the SQL rows, or a statement supported by at
least one retrieved chunk. An answer that invents figures, names categories
not in the rows, or asserts policy not in any chunk is not grounded. An
answer that makes no claims beyond honestly stating the sources do not cover
the question is grounded: it tells no lies.

confidence: how well the answer actually RESOLVES the user's question using
the sources, from 0.0 to 1.0. This is a SEPARATE judgment from grounded, and
the two routinely disagree.

Resolving the question is NOT the same as correctly identifying that the
sources cannot answer it. Both are honest. Only the first earns high
confidence. Do not reward an articulate non-answer: fluent phrasing of "I
could not find this" is still a non-answer.

- An answer that fully and accurately answers the question from the sources
  is high confidence (0.8 or above).
- An answer that says, in ANY phrasing, that the sources do not cover the
  question, that the information is not in the provided documents, that no
  relevant policy or measure exists, or any equivalent "I cannot find this"
  or "I do not know from these sources" framing, MUST score below 0.7. This
  holds no matter how confidently or fluently the non-answer is written.
  Correctly naming the gap is honest, but the user's question was not
  resolved, so it is a confidence failure.
- An answer that resolves only part of the question, or hedges on the part
  that matters, is also below 0.7.

Two concrete examples on this corpus, both currently easy to over-score:
- Question: "What is Olist's policy on cryptocurrency payments?" Answer: "The
  corpus does not contain a policy document on cryptocurrency payments, so I
  cannot answer." Grounded (it invents nothing), but confidence is LOW
  (around 0.2): the question was not resolved, the policy was simply absent.
- Question: "How are damaged items handled when the seller is at fault?"
  Answer: "The documents do not specify seller-fault damage handling; they
  only mention damage in transit." Grounded, but confidence is LOW (around
  0.3): the specific question was not answered, only adjacent material was
  found. The presence of related-but-off-target chunks does NOT raise
  confidence.

Contrast: "What does order_status mean?" answered with the status values
listed in the chunk is high confidence (0.95): the question was fully
resolved from the source.

Use the review_answer tool to return both judgments. Whenever confidence is
below 0.7, propose a revised_query: a reformulated retrieval query likely to
surface the missing information on a second pass. Prefer concrete identifier
tokens the corpus uses (table names, column names, category names including
their Portuguese forms such as moveis_decoracao or cama_mesa_banho) over the
natural-language phrasing of the original question. When confidence is 0.7 or
above, set revised_query to null.
"""

_REVIEW_TOOL = {
    "name": "review_answer",
    "description": "Evaluate whether the synthesized answer is grounded in the provided sources.",
    "input_schema": {
        "type": "object",
        "properties": {
            "confidence": {
                "type": "number",
                "description": (
                    "0.0 to 1.0. How well the answer resolves the question using the "
                    "sources. Any 'the sources do not cover this' / 'I cannot find this' "
                    "non-answer MUST be below 0.7 even when grounded and fluently worded, "
                    "because the question was not resolved. High (0.8+) only when the "
                    "answer actually resolves the question from the sources."
                ),
            },
            "grounded": {
                "type": "boolean",
                "description": (
                    "True if every factual claim in the answer traces to a source "
                    "(a SQL row or a retrieved chunk). False if any claim is unsupported."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "Brief explanation of the assessment. If grounded is false, name "
                    "which claims lacked support."
                ),
            },
            "revised_query": {
                "type": ["string", "null"],
                "description": (
                    "If confidence < 0.7, a reformulated retrieval query that would likely "
                    "find the missing information on a second pass. Otherwise null. "
                    "Examples: original 'furniture returns' might become 'moveis_decoracao "
                    "moveis_sala return policy' if the issue is missing category-specific "
                    "chunks."
                ),
            },
        },
        "required": ["confidence", "grounded", "reasoning", "revised_query"],
    },
}

# Route-specific evaluation criteria appended to the user prompt. The system
# prompt explains grounding generically; this tells the reviewer which sources
# to hold the answer against for the route that actually ran.
_ROUTE_CRITERIA = {
    "sql": (
        "Route: sql. Check that every number and category named in the answer "
        "appears in the SQL rows. Flag any value not present in the rows."
    ),
    "rag": (
        "Route: rag. Check that every claim in the answer is supported by at "
        "least one retrieved chunk. Flag claims that do not appear in any chunk."
    ),
    "hybrid": (
        "Route: hybrid. Both checks apply. Every number must match the SQL rows "
        "AND every prose claim must be supported by at least one retrieved chunk."
    ),
}


class ReviewResult(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    grounded: bool
    reasoning: str
    revised_query: str | None = None


class Reviewer:
    def __init__(self) -> None:
        self._client = maybe_trace(
            anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        )

    def review(self, state: OrchestratorState) -> ReviewResult:
        """Score whether the synthesized answer is grounded in the state's sources."""
        route = state.get("route") or "hybrid"
        user_prompt = self._build_user_prompt(state, route)

        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=[_REVIEW_TOOL],
            tool_choice={"type": "tool", "name": "review_answer"},
            messages=[{"role": "user", "content": user_prompt}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "review_answer":
                result = ReviewResult.model_validate(block.input)
                logger.info(
                    "reviewer: route=%s grounded=%s confidence=%.2f revised=%r",
                    route,
                    result.grounded,
                    result.confidence,
                    result.revised_query,
                )
                return result

        # Forced tool_choice should make this unreachable. If the model returns
        # no tool call, treat it as ungrounded with no fix so the loop ends
        # rather than spinning on a missing decision.
        logger.warning("reviewer: no tool_use block returned; treating as ungrounded")
        return ReviewResult(
            confidence=0.0,
            grounded=False,
            reasoning="Reviewer returned no structured assessment.",
            revised_query=None,
        )

    @staticmethod
    def _build_user_prompt(state: OrchestratorState, route: str) -> str:
        query = state["query"]
        synthesis = state.get("synthesis") or {}
        answer = synthesis.get("answer", "(no answer was produced)")

        parts: list[str] = [
            f"User question:\n{query}",
            f"Synthesized answer to evaluate:\n{answer}",
        ]

        parts.append(Reviewer._format_sql(state))
        parts.append(Reviewer._format_chunks(state))
        parts.append(_ROUTE_CRITERIA.get(route, _ROUTE_CRITERIA["hybrid"]))
        parts.append(
            "Judge whether the answer is grounded in the sources above and call "
            "review_answer."
        )
        return "\n\n".join(parts)

    @staticmethod
    def _format_sql(state: OrchestratorState) -> str:
        sql_result = state.get("sql_result")
        if not sql_result:
            return "SQL rows: none (no database query ran for this question)."
        if sql_result.get("status") != "success" or not sql_result.get("response"):
            reason = sql_result.get("failure_reason") or "unknown"
            return f"SQL rows: query did not succeed (reason: {reason})."

        resp = sql_result["response"]
        columns = resp["columns"]
        rows = resp["rows"]
        lines = [f"SQL rows from the {resp['resolved']['measure']} measure ({resp['row_count']} rows):"]
        lines.append(" | ".join(columns))
        for row in rows:
            lines.append(" | ".join(str(row[c]) for c in columns))
        return "\n".join(lines)

    @staticmethod
    def _format_chunks(state: OrchestratorState) -> str:
        chunks = state.get("rag_chunks") or []
        if not chunks:
            return "Retrieved chunks: none."
        lines = ["Retrieved chunks (top 5, source then content):"]
        for i, chunk in enumerate(chunks[:5], start=1):
            lines.append(
                f"\n[{i}] source: {chunk.get('source')} | section: {chunk.get('section')}\n"
                f"{chunk.get('content')}"
            )
        return "\n".join(lines)
