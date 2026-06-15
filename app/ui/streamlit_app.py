"""
SemaFlow trust-layer UI (Stage 5).

A thin Streamlit surface over Orchestrator.run(query). The point is not the
answer alone but the receipts: which route fired, the SQL that ran, the chunks
retrieved, and the reviewer's verdict including any self-correction. Most
"chat with your data" demos show only the prose. This shows the prose plus the
evidence, which is the whole governance story.

Run from the repo root:

    streamlit run app/ui/streamlit_app.py

Requires the semaflow_db container running and ANTHROPIC_API_KEY in .env
(router, SQL node, synthesizer, and reviewer all call Claude).

Async note: the orchestrator's sql_node bridges to the async SQL pipeline via
asyncio.run(...). Verified (scripts/probes/streamlit_async_check.py) that
Streamlit's script-runner thread has no already-running event loop, so that
pattern works here unchanged. No nest_asyncio, no refactor.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Make app/ importable when Streamlit runs this file by path.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

load_dotenv()

from app.orchestrator.graph import CONFIDENCE_THRESHOLD, Orchestrator  # noqa: E402

# Sample queries, one per route shape plus the locked hedge demo. The hybrid
# sample is the Stage 5 checkpoint question (single SQL concept + single
# well-covered RAG concept), not the brief's 5-category version, which dilutes
# retrieval against top_k=5 and fires the revision loop. See the checkpoint
# test docstring.
SAMPLE_QUERIES: dict[str, str] = {
    "SQL": "Show me the top 5 product categories by revenue",
    "RAG": "What does order_status mean and what are its possible values?",
    "Hybrid": "What is the average order value by state, and what does customer_state mean?",
    "Hedge demo": "How are damaged items handled when the seller is at fault?",
}

ROUTE_COLOR = {"sql": "blue", "rag": "violet", "hybrid": "green"}


@st.cache_resource(show_spinner="Loading orchestrator (models + clients)...")
def get_orchestrator() -> Orchestrator:
    """Build the orchestrator once per server process. It loads two transformer
    models and a BM25 index, so this must not run on every rerun."""
    return Orchestrator()


# ── rendering helpers ────────────────────────────────────────────────────────

def _escape_md(text: str) -> str:
    """Escape characters Streamlit markdown would mis-render. Currency '$'
    triggers LaTeX math mode, so a pair like 'R$772 ... R$708' renders the text
    between them as math and splits it into gibberish glyphs."""
    return text.replace("\\", "\\\\").replace("$", "\\$")


# ── chart helpers ────────────────────────────────────────────────────────────

def _infer_types(rows: list[dict], cols: list[str]) -> dict[str, str]:
    types: dict[str, str] = {}
    for col in cols:
        values = [r[col] for r in rows if r.get(col) is not None]
        if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            types[col] = "numeric"
        elif "date" in col.lower():
            types[col] = "datetime"
        else:
            types[col] = "categorical"
    return types


def auto_chart(rows: list[dict]) -> None:
    """Pick a chart from the row shape. One numeric + one low-cardinality
    categorical -> bar. One numeric + one datetime -> line. Otherwise table.
    Built-in charts only, no Plotly/Altair."""
    if not rows:
        st.info("No rows returned.")
        return

    df = pd.DataFrame(rows)
    cols = list(rows[0].keys())
    types = _infer_types(rows, cols)
    numerics = [c for c in cols if types[c] == "numeric"]
    cats = [c for c in cols if types[c] == "categorical"]
    dates = [c for c in cols if types[c] == "datetime"]

    if len(numerics) == 1 and len(cats) == 1 and df[cats[0]].nunique() < 30:
        st.bar_chart(df.set_index(cats[0])[numerics[0]])
    elif len(numerics) == 1 and len(dates) == 1:
        st.line_chart(df.set_index(dates[0])[numerics[0]])
    st.dataframe(df, width="stretch")


# ── trust-layer badges ───────────────────────────────────────────────────────

def render_trust_badges(state: dict) -> None:
    route = state.get("route") or "unknown"
    confidence = state.get("confidence") or 0.0
    grounded = bool(state.get("grounded"))
    revision_count = state.get("revision_count") or 0

    route_color = ROUTE_COLOR.get(route, "gray")

    if confidence >= 0.85:
        conf_color = "green"
    elif confidence >= CONFIDENCE_THRESHOLD:
        conf_color = "orange"
    else:
        conf_color = "red"

    cols = st.columns(4)
    cols[0].markdown(f":{route_color}-badge[Route: {route}]")
    cols[1].markdown(f":{conf_color}-badge[Confidence: {confidence:.2f}]")
    if grounded:
        cols[2].markdown(":green-badge[Grounded ✓]")
    else:
        cols[2].markdown(":red-badge[Grounded ✗]")
    if revision_count > 0:
        label = "Self-corrected once" if revision_count == 1 else f"Revised ×{revision_count}"
        cols[3].markdown(f":orange-badge[{label}]")


# ── result sections ──────────────────────────────────────────────────────────

def render_sql_details(state: dict) -> None:
    sql_result = state.get("sql_result")
    with st.expander("SQL details", expanded=False):
        if not sql_result:
            st.write("No SQL path ran for this query.")
            return
        status = sql_result.get("status")
        if status != "success" or not sql_result.get("response"):
            st.warning(f"SQL did not produce rows (status={status}).")
            reason = sql_result.get("failure_reason")
            if reason:
                st.write(reason)
            return

        resp = sql_result["response"]
        measure = resp["resolved"]["measure"]
        st.markdown(f"**Measure:** `{measure}`")
        params = resp["resolved"].get("parameters_applied") or {}
        if params:
            st.markdown(f"**Parameters:** `{params}`")

        auto_chart(resp.get("rows") or [])

        final_sql = resp.get("final_sql") or resp["resolved"].get("sql")
        if final_sql:
            st.markdown("**SQL executed:**")
            st.code(final_sql, language="sql")


def render_chunks(state: dict) -> None:
    rag_chunks = state.get("rag_chunks") or []
    with st.expander(f"Retrieved chunks ({len(rag_chunks)})", expanded=False):
        if not rag_chunks:
            st.write("No RAG path ran for this query.")
            return
        for i, chunk in enumerate(rag_chunks, start=1):
            source = chunk.get("source")
            section = chunk.get("section") or "—"
            st.markdown(f"**{i}. {source}** · {section}")
            st.write(_escape_md(chunk.get("content", "")))
            if i < len(rag_chunks):
                st.divider()


def render_reviewer(state: dict) -> None:
    confidence = state.get("confidence") or 0.0
    grounded = bool(state.get("grounded"))
    reasoning = state.get("review_reasoning") or ""
    revised_query = state.get("revised_query")
    revision_count = state.get("revision_count") or 0

    with st.expander("Reviewer details", expanded=False):
        if confidence >= 0.85:
            color = "green"
        elif confidence >= CONFIDENCE_THRESHOLD:
            color = "orange"
        else:
            color = "red"
        st.markdown(f"**Confidence:** :{color}[{confidence:.2f}]")
        st.markdown(f"**Grounded:** {'✓ yes' if grounded else '✗ no'}")
        st.markdown("**Reasoning:**")
        st.write(_escape_md(reasoning))
        if revision_count > 0 and revised_query:
            st.markdown("**Revised query (loop fired):**")
            st.code(revised_query)


# ── main render ──────────────────────────────────────────────────────────────

def render_result(state: dict) -> None:
    errors = state.get("errors") or []
    if errors:
        st.warning("The pipeline reported errors:\n\n" + "\n".join(f"- {e}" for e in errors))

    st.subheader("Answer")
    synthesis = state.get("synthesis")
    answer = (synthesis or {}).get("answer", "").strip()
    if answer:
        safe = _escape_md(answer)
        st.markdown(f"#### {safe}" if len(answer) < 120 else safe)
    else:
        st.info("No answer was produced.")

    render_trust_badges(state)
    st.divider()
    render_sql_details(state)
    render_chunks(state)
    render_reviewer(state)


def _set_query(q: str) -> None:
    st.session_state.query = q


def main() -> None:
    st.set_page_config(page_title="SemaFlow", layout="wide")
    st.title("SemaFlow")
    st.caption("Governed multi-agent analytics on Olist")

    if "query" not in st.session_state:
        st.session_state.query = ""

    st.text_input("Ask a question", key="query", placeholder="e.g. top 5 categories by revenue")

    st.write("Sample queries:")
    cols = st.columns(len(SAMPLE_QUERIES))
    for col, (label, q) in zip(cols, SAMPLE_QUERIES.items()):
        col.button(label, on_click=_set_query, args=(q,), width="stretch")

    submitted = st.button("Submit", type="primary")

    if submitted:
        query = st.session_state.query.strip()
        if not query:
            st.warning("Enter a question first.")
            return
        orchestrator = get_orchestrator()
        try:
            with st.spinner("Running pipeline..."):
                st.session_state.result = orchestrator.run(query)
                st.session_state.result_query = query
        except Exception as exc:  # noqa: BLE001 - surface, never crash the UI
            st.error("Something went wrong. Details below.")
            with st.expander("Traceback", expanded=False):
                st.code("".join(traceback.format_exception(exc)))
            st.session_state.pop("result", None)
            return

    result = st.session_state.get("result")
    if result:
        st.divider()
        st.caption(f"Showing result for: {st.session_state.get('result_query', '')}")
        render_result(result)


main()
