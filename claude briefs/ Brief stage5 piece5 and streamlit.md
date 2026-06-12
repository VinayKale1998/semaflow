# Brief for Claude Code: Stage 5 Piece 5 + Streamlit UI

**Scope:** Finish Stage 5 by building the checkpoint test (Piece 5), then build the Streamlit trust-layer UI. Single focused session, two clean deliverables.



**Current state:** Stage 5 Pieces 1-4 complete. Test suite at 32 tests, all green. LangSmith tracing live with LLM-level child spans. Reviewer recalibrated. q7 (damaged items) locked as the golden-set hedge demo.

---

## Part 1: Piece 5 — Stage 5 checkpoint test

### Purpose

A single integration test that proves the full Stage 5 pipeline works end to end on a hybrid question. This is the architectural checkpoint from the bible: _"a hybrid question flows end to end and a low-confidence answer escalates."_ The escalation half is already covered by the Piece 4 reviewer/loop tests. This test covers the happy-path half explicitly, as the official Stage 5 checkpoint.

### File

Create `app/orchestrator/tests/test_stage5_checkpoint.py`. New file. Do not bury this in `test_graph.py`. The point is that this is THE Stage 5 checkpoint, separate and explicit.

### Question to use

Use a hybrid question that resolves cleanly on first pass. Recommended:

> "Show me the top 5 product categories by revenue and explain what kind of products those categories contain."

This is the same shape as the existing hybrid test in `test_graph.py` and is known to route as hybrid, produce SQL rows, retrieve relevant category chunks, and synthesize a grounded answer on first pass. The point of this test is not to find a new question; it's to enforce a stricter set of assertions on a known-working flow.

If a different hybrid question is preferred (something not already in `test_graph.py` for separation), pick one that also routes hybrid and resolves first-pass. Document the choice in a comment.

### Assertions (all must hold)

python

```python
# 1. Routing
assert state["route"] == "hybrid"
assert state["route_confidence"] >= 0.7

# 2. Both paths produced content
assert state["sql_result"] is not None
assert state["sql_result"].rows  # non-empty
assert len(state["rag_chunks"]) > 0

# 3. Synthesizer produced an answer
assert state["synthesis"] is not None
assert state["synthesis"].answer  # non-empty string
assert state["synthesis"].has_sql is True
assert state["synthesis"].has_rag is True

# 4. Reviewer approved on first pass (no loop fire)
assert state["grounded"] is True
assert state["confidence"] >= 0.7
assert state["revision_count"] == 0

# 5. Grounding is real, not just claimed
# Pick at least one category name from sql_result.rows and assert it appears
# in synthesis.answer. Same for at least one term from a rag_chunk.
top_category = state["sql_result"].rows[0]["category"]  # or the right key
assert top_category in state["synthesis"].answer

chunk_content = state["rag_chunks"][0].content
# Pick a distinctive token from chunk_content and assert presence
# OR check sources_used contains the chunk's source file
assert any(
    chunk.source in state["synthesis"].sources_used
    for chunk in state["rag_chunks"]
)

# 6. Termination
# The test reaching this point already proves termination, but log it for clarity.
```

The fifth assertion is the most important. It enforces that the synthesizer actually used the retrieved sources, not just produced something coherent. Pick the assertion shape that's most stable against minor synthesis variation (e.g., assert that a category name appears, not an exact phrase).

### Verification

Run `pytest app/orchestrator/tests/test_stage5_checkpoint.py -v`. Must pass. Then run the full suite. Expected count: 32 → 33 (one new test added).

If the test is flaky (passes sometimes, fails others) due to synthesizer wording variance, tighten the assertions toward stable substrings (category names, source filenames) rather than full phrases. Do NOT mark it flaky and move on.

### Out of scope for Piece 5

- Do not add loop-firing assertions here. q7 already covers that.
- Do not add SQL-only or RAG-only checkpoints. Hybrid is the architectural checkpoint per the bible.
- Do not retry or wrap in `pytest.mark.flaky`.

---

## Part 2: Streamlit UI

### Purpose

A thin trust-layer interface over `Orchestrator.run(query)`. The UI is the proof, not the product. Most "chat with your database" demos show only the answer. SemaFlow's UI shows the answer **plus the receipts**: SQL that ran, chunks retrieved, reviewer's verdict, revision history. That visibility is the differentiator and the interview demo.

### File location

`app/ui/streamlit_app.py`. Create the `app/ui/` directory if it doesn't exist with an `__init__.py`. Run command: `streamlit run app/ui/streamlit_app.py`. Document this in the file's module docstring.

### Async handling check (do this first)

The orchestrator's `sql_node` uses `asyncio.run(...)` to bridge to the async SQL pipeline. The Stage 4 handoff flagged this pattern can break when called from an already-running event loop (FastAPI was named; Streamlit may have the same issue).

**Before writing UI code, verify:**

1. Can Streamlit invoke `Orchestrator.run(query)` (or whatever the entry point is) without an event loop conflict?
2. If it works, proceed. If it raises `RuntimeError: asyncio.run() cannot be called from a running event loop` or similar, fix the orchestrator entry point to handle this cleanly. The fix should be: detect if a loop is already running and use `asyncio.get_event_loop().run_until_complete(...)` or `nest_asyncio` (last resort) OR refactor the entry point to be properly async-aware.

Do not paper over this with a thread-local hack. If the entry point needs refactoring, refactor it. Document what was changed and why.

### Layout (locked)

```
+---------------------------------------------------------------+
|  SemaFlow                                                     |
|  Governed multi-agent analytics on Olist                      |
+---------------------------------------------------------------+
|                                                               |
|  [Query input field, full width]              [Submit button] |
|                                                               |
|  Sample queries: [SQL] [RAG] [Hybrid] [Hedge demo]            |
|                                                               |
+---------------------------------------------------------------+
|                                                               |
|  ANSWER                                                       |
|  [Synthesized prose, prominent, larger font]                  |
|                                                               |
|  [Route: hybrid] [Confidence: 0.87] [Grounded ✓]              |
|  [Revision: yes/no badge, only shown if revision_count > 0]   |
|                                                               |
+---------------------------------------------------------------+
|  ▶ SQL details (collapsed by default)                         |
|     • Measure: top_categories_by_revenue                      |
|     • Chart (auto-selected by row shape)                      |
|     • Data table                                              |
|     • SQL executed (code block, monospace)                    |
|  ▶ Retrieved chunks (collapsed by default)                    |
|     • For each chunk: source · section · content              |
|  ▶ Reviewer details (collapsed by default)                    |
|     • Confidence score with color                             |
|     • Grounded flag                                           |
|     • Reasoning text                                          |
|     • Revised query (only if loop fired)                      |
+---------------------------------------------------------------+
```

Use `st.expander` for the three collapsed sections. Use `st.columns` for the trust-layer badge row.

### Trust layer indicators

**Route badge.** Always visible. Use `st.markdown` with an inline colored badge:

- `sql` → blue
- `rag` → purple
- `hybrid` → green

**Confidence score.** Always visible. Numeric to two decimals, color-coded:

- `>= 0.85` → green
- `0.70 <= conf < 0.85` → yellow/amber
- `< 0.70` → red

**Grounded flag.** Always visible. ✓ green if `grounded == True`, ✗ red if False.

**Revision badge.** Conditional. Only render if `revision_count > 0`. Amber color, label like "Revised once" or "Self-corrected once".

### Auto-charting rules

In the SQL details section, inspect `sql_result.rows` and apply:

python

```python
# Detect column types from the first row
def auto_chart(rows):
    if not rows:
        return None

    cols = list(rows[0].keys())
    types = infer_types(rows, cols)  # dict of col -> "numeric"|"categorical"|"datetime"

    numerics = [c for c in cols if types[c] == "numeric"]
    cats = [c for c in cols if types[c] == "categorical"]
    dates = [c for c in cols if types[c] == "datetime"]

    df = pd.DataFrame(rows)

    if len(numerics) == 1 and len(cats) == 1 and df[cats[0]].nunique() < 30:
        # Bar chart
        st.bar_chart(df.set_index(cats[0])[numerics[0]])
    elif len(numerics) == 1 and len(dates) == 1:
        # Line chart
        st.line_chart(df.set_index(dates[0])[numerics[0]])
    else:
        # Table only
        st.dataframe(df)
        return
```

Use pandas for the DataFrame conversion. Use built-in `st.bar_chart`, `st.line_chart`, `st.dataframe`. **Do not import Plotly, Altair, or any external plotting library.**

Type inference can be simple:

- If all values in a column are int/float → numeric.
- If column name contains "date" or values parse as ISO dates → datetime.
- Otherwise → categorical.

### Sample queries

Below the input field, render 4 buttons that populate the input on click:

1. **SQL example**: "Show me the top 5 product categories by revenue"
2. **RAG example**: "What does order_status mean and what are its possible values?"
3. **Hybrid example**: "Show me the top 5 product categories by revenue and explain what those categories contain"
4. **Hedge demo**: "How are damaged items handled when the seller is at fault?"

Each button sets the query text. The user can then hit Submit. This makes the UI immediately usable without thinking of a question and gives a clean walkthrough path.

Implementation: use `st.session_state` to store the current query text, set it from button clicks, render the input bound to that state. (This is the ONLY use of session state in the UI. Each query is still independent. No conversation history.)

### Error handling

If `Orchestrator.run(query)` raises an exception:

- Show a red `st.error` box with a concise message ("Something went wrong. Details below.")
- Show the exception traceback in a collapsed `st.expander`.
- Do not crash the UI.

If the orchestrator returns a state with errors in the `errors` list, surface them in an amber `st.warning` box above the answer.

### Loading state

Wrap the orchestrator call in `with st.spinner("Running pipeline..."):`. The spinner is enough; do not add custom progress bars.

### Code structure

Keep it pragmatic. Single file is fine unless it goes over 400 lines. If it does, extract:

- `app/ui/components.py` for the badge/indicator render helpers.
- `app/ui/charting.py` for the auto-chart logic.

Do not over-modularize. This is a UI script, not a framework.

### What the UI deliberately does NOT do (locked)

- No charts on RAG-only or synthesis-only responses.
- No external plotting library (Plotly, Altair, etc.).
- No conversation history. Each query independent.
- No login, no telemetry beyond the existing LangSmith hooks.
- No streaming responses. Synchronous.
- No custom CSS beyond Streamlit defaults.
- No download/export buttons.
- No comparison view between two queries.

### Verification

1. `streamlit run app/ui/streamlit_app.py` starts cleanly.
2. Submit each of the four sample queries. All four return without error.
3. Verify the trust layer renders correctly for each:
    - SQL query: route badge "sql", chart appears in SQL details, no chunks section content.
    - RAG query: route badge "rag", chunks section has content, no SQL details chart.
    - Hybrid query: both populated.
    - Hedge demo: confidence < 0.7 (red), grounded ✗, revision badge visible, reviewer reasoning shows the hedge logic.
4. Open LangSmith. Confirm fresh traces appear for the queries submitted via the UI. The traces should look identical to traces from `pytest` runs.
5. Take a screenshot of the hedge demo run (the one with the revision badge visible). This is the agentic-loop demo for the LinkedIn walkthrough.

### Things to flag if encountered

- If `Orchestrator.run` doesn't exist as the entry point (the orchestrator class might expose a different method), use whatever the actual top-level invocation is and document in the docstring.
- If async handling requires `nest_asyncio` as the only viable fix, install it as a dependency and document why in a comment. Prefer a clean refactor first.
- If any sample query fails or returns ungrounded unexpectedly, do NOT change the question to make it pass. Report the failure, capture the trace, surface it for review.

---

## Order of operations

1. Piece 5 checkpoint test first. Quick, low-risk, locks the architectural checkpoint.
2. Streamlit async handling check. Verify the orchestrator can be invoked from Streamlit before writing UI code.
3. Streamlit UI build, layout first, then auto-charting, then sample queries and error handling.
4. End-to-end smoke test through the UI for all four sample queries.
5. Final test suite run. All previously passing tests still pass. New count: 33.
6. Commit everything as a clean unit: "Stage 5 complete: checkpoint test + Streamlit trust-layer UI."

---

## Final verification checklist (paste back when done)

- [ ]  `test_stage5_checkpoint.py` passes, asserts route=hybrid, grounded=True, revision_count=0, sources actually referenced in answer.
- [ ]  Full suite: 33 tests, all green.
- [ ]  Async handling verified. Note any refactor in commit message.
- [ ]  Streamlit app starts with `streamlit run app/ui/streamlit_app.py`.
- [ ]  All four sample queries execute successfully through the UI.
- [ ]  Trust layer indicators render correctly for each route type.
- [ ]  Auto-charting fires on the SQL example (bar chart) and stays silent on RAG-only.
- [ ]  Hedge demo shows revision badge, low confidence (red), and reviewer reasoning text.
- [ ]  Fresh LangSmith traces appear from UI-submitted queries.
- [ ]  Screenshot of the hedge demo run saved (for the walkthrough video).
- [ ]  CLAUDE.md and `memory/project_semaflow.md` updated: Stage 5 fully complete, Streamlit UI shipped.
- [ ]  One clean commit.

---

## Working rules (carry these)

- No em dashes. Plain English. Direct, slightly dry, never motivational.
- Push back on scope. If a "nice to have" comes up mid-build (multi-query comparison, custom CSS, conversation history), defer it. The locked scope above is the locked scope.
- Every component traces to a "why." If something doesn't have a real reason, don't ship it.
- The UI is the proof, not the product. Receipts visible. No glossy fluff.
- If anything blocks meaningfully (async refactor longer than 30 min, charting issues, test instability), surface it instead of working around it silently.

---

## What's next after this

Stage 5 done. The remaining items are:

- Stage 6 (evals): golden set expansion to 30-50 questions, eval harness, regression runner. Not blocking the demo.
- Restore Gemini Flash as workhorse once GCP billing is enabled. Interface change is single-file per the handoff.
- LinkedIn walkthrough video using the Streamlit UI and the hedge demo trace.
- Portfolio update: SemaFlow moves from "in progress" to "complete v1 demo, evals in progress."