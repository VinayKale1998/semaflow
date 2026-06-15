"""
Stage 5, Piece 3: Synthesizer node.

Takes the orchestrator state after SQL and/or RAG have run and produces a
natural-language answer grounded only in the supplied rows and chunks.
Uses Claude Sonnet (prose-quality step, unlike the Haiku router).

No tool use: the LLM returns plain text. The Pydantic SynthesisResult
wrapping carries metadata (sources_used, has_sql, has_rag) that is derived
in code from the input state, not from the model.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from app.llm.tracing import maybe_trace

if TYPE_CHECKING:
    from app.orchestrator.graph import OrchestratorState

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500

_SYSTEM_PROMPT = """\
You convert structured analytics results and document excerpts into a clear,
accurate natural-language answer for an analytics system built on the Olist
Brazilian e-commerce dataset.

Rules:
- Grounding: every number in your answer must come from the SQL result
  provided. Every factual claim about data structure, columns, or policy
  must come from the document excerpts provided. Do not invent figures or
  facts.
- Honesty: if the SQL result is empty or failed, say so plainly and give the
  reason. If the document excerpts do not cover the question, say you do not
  have that information in the corpus. Never fabricate to fill a gap.
- No internal source names: do not name document filenames (anything ending
  in .md), measure names, or raw table/column identifiers in the answer. The
  reader is a business user; the provenance is surfaced separately by the
  interface. Speak in plain business terms (say "health and beauty", not
  "health_beauty" or "the top_categories_by_revenue measure"). No footnotes,
  no links.
- Voice: direct, factual, slightly dry. Plain English. No marketing tone, no
  exclamation marks, no preambles such as "I'd be happy to help". Do not use
  markdown, section headers, or emojis unless the question explicitly asks
  for formatting.
- Length: concise. Answer the question and stop.
"""


class SynthesisResult(BaseModel):
    answer: str
    sources_used: list[str]
    has_sql: bool
    has_rag: bool


class Synthesizer:
    def __init__(self) -> None:
        self._client = maybe_trace(
            anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        )

    def synthesize(self, state: OrchestratorState) -> SynthesisResult:
        query: str = state["query"]
        sql_result = state.get("sql_result")
        rag_chunks = state.get("rag_chunks") or []

        sql_ok = bool(sql_result) and sql_result.get("status") == "success"
        rows: list[dict] = (
            sql_result["response"]["rows"] if sql_ok and sql_result["response"] else []
        )
        has_sql = bool(rows)
        has_rag = bool(rag_chunks)

        sources_used = self._collect_sources(sql_result, sql_ok, rag_chunks)
        user_prompt = self._build_user_prompt(query, sql_result, sql_ok, rag_chunks)

        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        answer = response.content[0].text.strip()

        logger.info(
            "synthesizer: query=%r has_sql=%s has_rag=%s sources=%s",
            query,
            has_sql,
            has_rag,
            sources_used,
        )
        return SynthesisResult(
            answer=answer,
            sources_used=sources_used,
            has_sql=has_sql,
            has_rag=has_rag,
        )

    @staticmethod
    def _collect_sources(
        sql_result: dict | None, sql_ok: bool, rag_chunks: list[dict]
    ) -> list[str]:
        """Derive contributing sources from the state, not the model."""
        sources: list[str] = []
        if sql_ok and sql_result["response"]:
            measure = sql_result["response"]["resolved"]["measure"]
            sources.append(measure)
        for chunk in rag_chunks:
            src = chunk.get("source")
            if src and src not in sources:
                sources.append(src)
        return sources

    @staticmethod
    def _build_user_prompt(
        query: str, sql_result: dict | None, sql_ok: bool, rag_chunks: list[dict]
    ) -> str:
        parts: list[str] = [f"Original question:\n{query}\n"]

        # SQL section
        if sql_result is None:
            parts.append("SQL result: none (no database query was run for this question).")
        elif sql_ok and sql_result["response"]:
            resp = sql_result["response"]
            measure = resp["resolved"]["measure"]
            columns = resp["columns"]
            rows = resp["rows"]
            lines = [f"SQL result from the {measure} measure ({resp['row_count']} rows):"]
            lines.append(" | ".join(columns))
            for row in rows:
                lines.append(" | ".join(str(row[c]) for c in columns))
            parts.append("\n".join(lines))
        else:
            reason = sql_result.get("failure_reason") or "unknown error"
            status = sql_result.get("status")
            parts.append(
                f"SQL result: could not be computed (status={status}). "
                f"Reason: {reason}"
            )

        # RAG section
        if rag_chunks:
            chunk_lines = ["Document excerpts (most relevant first):"]
            for i, chunk in enumerate(rag_chunks[:5], start=1):
                chunk_lines.append(
                    f"\n[{i}] source: {chunk.get('source')} | "
                    f"section: {chunk.get('section')}\n{chunk.get('content')}"
                )
            parts.append("\n".join(chunk_lines))
        else:
            parts.append("Document excerpts: none retrieved.")

        parts.append(
            "Synthesize an answer to the question using ONLY the material above. "
            "Do not add facts or numbers that are not present here."
        )
        return "\n\n".join(parts)
