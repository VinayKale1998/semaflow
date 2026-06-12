# SemaFlow Stage 5, Piece 3: Synthesizer Node

## Goal
Build `app/orchestrator/synthesizer.py`. Takes the orchestrator's state 
after SQL and/or RAG have run, produces a natural-language answer 
grounded in the actual sources. Wire it into the graph as a new node 
that runs after sql_node / rag_node / hybrid_node and before END.

## Why this exists
Today the orchestrator returns raw SQL rows and raw chunks. A user 
asking "top 5 categories by revenue and what they contain" gets back 
a dict of rows and a list of chunk dicts. The synthesizer turns that 
into the actual answer in prose.

## Interface
```python
class Synthesizer:
    def __init__(self) -> None:
        # Anthropic client. Use Claude Sonnet (claude-sonnet-4-6).
        # Sonnet, not Haiku, because synthesis is the prose-quality step.
        ...
    
    def synthesize(self, state: OrchestratorState) -> SynthesisResult:
        # Reads state["query"], state["sql_result"], state["rag_chunks"].
        # Returns the natural-language answer plus the sources used.
        ...
```

## SynthesisResult model
```python
class SynthesisResult(BaseModel):
    answer: str           # the natural-language answer
    sources_used: list[str]   # filenames or measure names that contributed
    has_sql: bool         # whether SQL rows were available
    has_rag: bool         # whether RAG chunks were available
```

## What the synthesizer prompts Claude to do

System prompt should establish:
- Role: convert structured analytics results and document chunks into a 
  clear, accurate natural-language answer.
- Grounding rule: every numeric claim must come from the SQL rows. Every 
  factual claim about data structure or policy must come from the RAG 
  chunks. Do not invent.
- Honesty rule: if SQL returned no rows or RAG returned no relevant 
  chunks, say so plainly. Do not fabricate.
- Format rule: plain English, concise. No markdown formatting unless 
  asked. No section headers, no emojis. Match the SemaFlow voice 
  (direct, factual, slightly dry).
- Cite sources inline by source name when relevant 
  (e.g. "from fact_orders.md" or "from the top_categories_by_revenue 
  measure").

User prompt should contain:
- The original query.
- The SQL result (if any): formatted as a small table or list, with 
  column names and rows. If status is not "success", include the failure 
  reason instead.
- The RAG chunks (if any): each chunk's source, section, and content. 
  Up to top 5 chunks.
- Explicit instruction: synthesize an answer using ONLY this material.

## Constraints
- One file. Type hints. stdlib logging.
- Use Sonnet for the call. Cost is fine, quality matters here.
- Token budget: 1500 max_tokens for the response. Plenty for a 
  conversational answer.
- Do NOT use tool use for the synthesizer. It returns prose. The 
  Pydantic wrapping is just for the metadata (sources_used, has_sql, 
  has_rag), which gets derived from the input state, not from the LLM.
- The actual LLM call returns plain text. Wrap it into SynthesisResult 
  in code.
- Do NOT add streaming.
- Do NOT add caching.
- Read ANTHROPIC_API_KEY from .env via python-dotenv.

## Graph wiring update
Update `app/orchestrator/graph.py` to:
- Add `synthesizer_node` that calls `Synthesizer.synthesize(state)` and 
  returns `{"synthesis": result.model_dump()}`.
- Add `synthesis` field to `OrchestratorState`:
```python
  synthesis: dict | None
```
- Re-route the graph: instead of sql_node, rag_node, hybrid_node going 
  directly to END, they now all flow to synthesizer_node, which flows 
  to END.
- Instantiate Synthesizer once in `Orchestrator.__init__` (same pattern 
  as Router and Retriever).

## Edge cases the synthesizer must handle
- SQL succeeded, no RAG chunks: synthesize from rows only.
- RAG returned chunks, no SQL: synthesize from chunks only.
- Hybrid: SQL succeeded and RAG returned chunks. Combine.
- SQL failed (status != "success"): include the failure reason in the 
  answer ("The system couldn't compute this because: [reason]"). Still 
  synthesize whatever RAG provided.
- RAG returned nothing relevant: state "I don't have specific information 
  about that in the corpus" rather than inventing.

## Tests
`app/orchestrator/tests/test_synthesizer.py`. Three cases mirroring the 
orchestrator's three routes, each invoked through the full graph:

```python
SYNTHESIZER_CASES = [
    {
        "query": "Top 5 product categories by revenue.",
        "expected_route": "sql",
        "must_mention": ["health_beauty", "watches_gifts"],  # known top revenue categories from Stage 1
    },
    {
        "query": "What does order_status mean?",
        "expected_route": "rag",
        "must_mention": ["delivered", "canceled"],  # known status values from fact_orders
    },
    {
        "query": "Show me the top 5 product categories by revenue and explain what those categories contain.",
        "expected_route": "hybrid",
        "must_mention": ["health_beauty", "watches_gifts", "bed_bath"],  # mix of revenue + category content
    },
]
```

For each:
- Call `orchestrator.run(query)`.
- Assert `state["route"] == expected_route`.
- Assert `state["synthesis"]` is not None.
- Assert `state["synthesis"]["answer"]` is a non-empty string.
- Assert each string in `must_mention` appears in the answer (case-insensitive).
- Assert `state["errors"]` is empty.

Run with pytest. Show the full answers in the output for spot-checking 
voice and grounding.

## What NOT to do
- Do NOT build the reviewer or confidence gate yet. That's Piece 4.
- Do NOT add a "thinking" or "reasoning" step. The synthesizer composes, 
  it doesn't reason about whether to run more queries.
- Do NOT add markdown formatting to the answer unless the query asked 
  for it.
- Do NOT add citations as footnotes or links. Inline source mentions 
  only.
- Do NOT call additional tools. The synthesizer reads state, calls 
  Claude once, returns text.

## After building
1. Show me the test output, including the actual synthesized answers 
   for all three cases.
2. Spot-check the voice. The answers should be direct, factual, no 
   marketing tone, no exclamation marks, no "I'd be happy to help" 
   preambles.
3. If any answer reads off, flag it. We may need to tighten the system 
   prompt before moving on.

Stop after the test run.