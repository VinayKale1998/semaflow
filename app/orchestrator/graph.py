"""
Stage 5 LangGraph orchestrator (Pieces 2, 3, 4).

Takes a query, runs the router, dispatches to the SQL pipeline, the RAG
retriever, or both, then synthesizes an answer and reviews it for
groundedness. If the reviewer is not confident the answer is supported by
its sources, the graph loops back once through a revised retrieval pass and
re-synthesizes. One revision maximum, then it ends with whatever it has. No
streaming.

The router and retriever are instantiated once at init (both are heavy:
the router holds an Anthropic client, the retriever loads two transformer
models and builds a BM25 index). The graph is compiled once. Execution is
cheap after that.

SQL execution goes through app.sql.pipeline.run_sql_pipeline, the Stage 3
facade. That function is async and returns a PipelineResult that tags
normal failures (no measure matched, guardrail violation, etc.) as a
status rather than raising, so a non-success SQL outcome does not land in
state["errors"]; only unexpected exceptions do.
"""
import asyncio
import logging
import os
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from app.orchestrator.reviewer import Reviewer
from app.orchestrator.router import Router
from app.orchestrator.synthesizer import Synthesizer
from app.rag.retriever import Retriever
from app.sql.pipeline import run_sql_pipeline

logger = logging.getLogger(__name__)

# Approve an answer only at or above this groundedness confidence. Below it
# (or if the reviewer flags the answer as not grounded) the graph loops back
# once for a revised retrieval pass. Static for v1. Tune once the golden set
# reaches 30-50 questions in Stage 6.
CONFIDENCE_THRESHOLD = 0.7


class OrchestratorState(TypedDict):
    query: str
    route: Literal["sql", "rag", "hybrid"] | None
    route_reason: str | None
    route_confidence: float | None
    sql_result: dict | None       # PipelineResult.model_dump(), or None on unexpected failure
    rag_chunks: list | None       # [Chunk.model_dump(), ...], or None on unexpected failure
    synthesis: dict | None        # SynthesisResult.model_dump(), set by synthesizer_node
    confidence: float             # reviewer groundedness confidence, 0.0 to 1.0
    grounded: bool                # reviewer verdict: every claim traces to a source
    review_reasoning: str         # why the reviewer scored this way
    revised_query: str | None     # reformulated query for the revision pass; None on first pass
    revision_count: int           # 0 on first pass, hard cap at 1
    errors: list[str]             # unexpected node exceptions only


class Orchestrator:
    def __init__(self) -> None:
        load_dotenv()
        self._check_tracing()
        logger.info("Orchestrator: loading Router, Retriever, Synthesizer (one-time, heavy)")
        self.router = Router()
        self.retriever = Retriever()
        self.synthesizer = Synthesizer()
        self.reviewer = Reviewer()
        self._graph = self._build_graph()

    @staticmethod
    def _check_tracing() -> None:
        tracing = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
        if tracing and os.environ.get("LANGSMITH_API_KEY"):
            logger.info(
                "LangSmith tracing enabled (project=%s)",
                os.environ.get("LANGSMITH_PROJECT", "default"),
            )
        else:
            logger.warning(
                "LangSmith tracing disabled: LANGSMITH_TRACING/LANGSMITH_API_KEY "
                "not set. Proceeding without traces."
            )

    def _build_graph(self):
        builder = StateGraph(OrchestratorState)
        builder.add_node("router", self._router_node)
        builder.add_node("sql", self._sql_node)
        builder.add_node("rag", self._rag_node)
        builder.add_node("hybrid", self._hybrid_node)
        builder.add_node("synthesizer", self._synthesizer_node)
        builder.add_node("reviewer", self._reviewer_node)
        builder.add_node("revision_retrieval", self._revision_retrieval_node)

        builder.add_edge(START, "router")
        builder.add_conditional_edges(
            "router",
            self._route_selector,
            {"sql": "sql", "rag": "rag", "hybrid": "hybrid"},
        )
        # All result nodes flow into the synthesizer, then into the reviewer.
        builder.add_edge("sql", "synthesizer")
        builder.add_edge("rag", "synthesizer")
        builder.add_edge("hybrid", "synthesizer")
        builder.add_edge("synthesizer", "reviewer")

        # Reviewer either ends the run or loops back once through a revised
        # retrieval pass. revision_retrieval re-enters the synthesizer, which
        # re-enters the reviewer. The one-shot cap lives in route_after_review:
        # once revision_count >= 1 it always ends, so the cycle cannot spin.
        builder.add_conditional_edges(
            "reviewer",
            self._route_after_review,
            {"end": END, "revise": "revision_retrieval"},
        )
        builder.add_edge("revision_retrieval", "synthesizer")
        return builder.compile()

    @staticmethod
    def _route_selector(state: OrchestratorState) -> str:
        # Router defaults to hybrid if it ever fails to decide, so does this.
        return state["route"] or "hybrid"

    # ── nodes ─────────────────────────────────────────────────────────────────

    def _router_node(self, state: OrchestratorState) -> dict:
        decision = self.router.classify(state["query"])
        logger.info(
            "router_node: route=%s confidence=%.2f",
            decision.route,
            decision.confidence,
        )
        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "route_confidence": decision.confidence,
        }

    def _run_sql(self, query: str) -> dict:
        """SQL logic shared by sql_node and hybrid_node.

        run_sql_pipeline is async and reports normal failures as a status,
        so its result is always a dict here. Only an unexpected raise lands
        in errors.
        """
        try:
            result = asyncio.run(run_sql_pipeline(query))
            return {"sql_result": result.model_dump()}
        except Exception as exc:  # noqa: BLE001 - node boundary, record and continue
            logger.exception("sql_node: unexpected failure")
            return {"sql_result": None, "errors": [f"sql_node: {exc}"]}

    def _run_rag(self, query: str) -> dict:
        """RAG logic shared by rag_node and hybrid_node."""
        try:
            chunks = self.retriever.retrieve(query, top_k=5, doc_type=None)
            return {"rag_chunks": [c.model_dump() for c in chunks]}
        except Exception as exc:  # noqa: BLE001 - node boundary, record and continue
            logger.exception("rag_node: unexpected failure")
            return {"rag_chunks": None, "errors": [f"rag_node: {exc}"]}

    def _sql_node(self, state: OrchestratorState) -> dict:
        return self._run_sql(state["query"])

    def _rag_node(self, state: OrchestratorState) -> dict:
        return self._run_rag(state["query"])

    def _hybrid_node(self, state: OrchestratorState) -> dict:
        """Run SQL then RAG sequentially and merge both updates."""
        sql_out = self._run_sql(state["query"])
        rag_out = self._run_rag(state["query"])

        merged: dict = {}
        merged.update({k: v for k, v in sql_out.items() if k != "errors"})
        merged.update({k: v for k, v in rag_out.items() if k != "errors"})

        errors = sql_out.get("errors", []) + rag_out.get("errors", [])
        if errors:
            merged["errors"] = errors
        return merged

    def _synthesizer_node(self, state: OrchestratorState) -> dict:
        try:
            result = self.synthesizer.synthesize(state)
            return {"synthesis": result.model_dump()}
        except Exception as exc:  # noqa: BLE001 - node boundary, record and continue
            logger.exception("synthesizer_node: unexpected failure")
            return {"synthesis": None, "errors": [f"synthesizer_node: {exc}"]}

    def _reviewer_node(self, state: OrchestratorState) -> dict:
        try:
            result = self.reviewer.review(state)
            return {
                "confidence": result.confidence,
                "grounded": result.grounded,
                "review_reasoning": result.reasoning,
                "revised_query": result.revised_query,
            }
        except Exception as exc:  # noqa: BLE001 - node boundary, record and continue
            # A reviewer failure must not strand the graph. Record it and end
            # with whatever the synthesizer produced: treat as grounded so
            # route_after_review sends us to END rather than into a revision
            # we cannot score.
            logger.exception("reviewer_node: unexpected failure")
            return {
                "confidence": 0.0,
                "grounded": True,
                "review_reasoning": f"reviewer failed: {exc}",
                "revised_query": None,
                "errors": [f"reviewer_node: {exc}"],
            }

    def _revision_retrieval_node(self, state: OrchestratorState) -> dict:
        """One-shot revised retrieval. Route-aware.

        SQL-only: re-retrieval does not apply (the SQL pipeline resolves from
        declared measures, not free text), so just bump the count and let the
        synthesizer try again with the same rows. RAG and hybrid re-retrieve
        with the reviewer's reformulated query and replace the chunk set.
        """
        revision_count = state["revision_count"] + 1
        route = state.get("route") or "hybrid"
        revised_query = state.get("revised_query")

        if route == "sql" or not revised_query:
            return {"revision_count": revision_count}

        try:
            chunks = self.retriever.retrieve(revised_query, top_k=5, doc_type=None)
            logger.info(
                "revision_retrieval: revised_query=%r returned %d chunks",
                revised_query,
                len(chunks),
            )
            return {
                "rag_chunks": [c.model_dump() for c in chunks],
                "revision_count": revision_count,
            }
        except Exception as exc:  # noqa: BLE001 - node boundary, record and continue
            logger.exception("revision_retrieval_node: unexpected failure")
            return {
                "revision_count": revision_count,
                "errors": [f"revision_retrieval_node: {exc}"],
            }

    @staticmethod
    def _route_after_review(state: OrchestratorState) -> str:
        approved = state["grounded"] and state["confidence"] >= CONFIDENCE_THRESHOLD
        if approved:
            return "end"
        if state["revision_count"] >= 1:
            return "end"  # already revised once, end with whatever we have
        if state["revised_query"] is None:
            return "end"  # reviewer proposed no fix, nothing to retry with
        return "revise"

    # ── public interface ───────────────────────────────────────────────────────

    def run(self, query: str) -> OrchestratorState:
        initial: OrchestratorState = {
            "query": query,
            "route": None,
            "route_reason": None,
            "route_confidence": None,
            "sql_result": None,
            "rag_chunks": None,
            "synthesis": None,
            "confidence": 0.0,
            "grounded": False,
            "review_reasoning": "",
            "revised_query": None,
            "revision_count": 0,
            "errors": [],
        }
        return self._graph.invoke(initial)
