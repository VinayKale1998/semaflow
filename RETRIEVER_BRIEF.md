# SemaFlow Stage 4: Retrieval Interface + Checkpoint Test

## Goal
Build `app/rag/retriever.py` with a hybrid retriever (pgvector cosine + 
BM25, merged via RRF, reranked via cross-encoder). Then build 
`app/rag/tests/test_stage4.py` to validate against expected source 
chunks for a small set of test queries.

## Dependencies to install
```bash
python -m pip install rank-bm25
```

`sentence-transformers` and `pgvector` are already installed. The 
cross-encoder ships with sentence-transformers.

## Interface
```python
class Retriever:
    def __init__(self) -> None:
        # Load embedding model, cross-encoder, open DB connection,
        # build BM25 index over all chunks
        ...
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[Chunk]:
        # Run hybrid retrieval and return top_k after reranking
        ...
```

## Pydantic model
```python
class Chunk(BaseModel):
    chunk_id: str
    source: str
    doc_type: str
    doc_title: str | None
    section: str | None
    content: str
    vector_distance: float | None = None
    bm25_score: float | None = None
    rrf_score: float | None = None
    reranker_score: float | None = None
```

---

## BUILD IN 3 PARTS. STOP AND SHOW OUTPUT AFTER EACH.

### Part A: Vector retrieval with metadata filtering

Add a private method `_vector_search(query, doc_type, k=50)`:
- Embed the query with `all-MiniLM-L6-v2`.
- Run pgvector query:

```sql
SELECT id, source, doc_type, doc_title, section, content,
       embedding <=> :q AS distance
FROM doc_chunks
WHERE (:dt IS NULL OR doc_type = :dt)
ORDER BY embedding <=> :q
LIMIT :k
```

- Return a list of Chunk objects with `vector_distance` populated.

**Stop here. Run this test:**
```python
r = Retriever()
results = r._vector_search("What does order_status mean?", doc_type=None, k=5)
for c in results:
    print(c.source, c.doc_type, c.section, round(c.vector_distance, 3))
```

Show me the output before continuing.

---

### Part B: BM25 retrieval + Reciprocal Rank Fusion

Build BM25 index at `Retriever.__init__` time:
- Load all chunks from doc_chunks into memory (id, content, doc_type).
- Tokenize each content string (lowercase, split on whitespace, strip 
  punctuation with a simple regex). Use the same tokenization for 
  queries.
- Initialize `BM25Okapi` from `rank_bm25` with the tokenized corpus.

Add a private method `_bm25_search(query, doc_type, k=50)`:
- Tokenize the query.
- Get scores for all chunks via `bm25.get_scores(tokenized_query)`.
- Apply doc_type filter in Python (filter scored chunks before sorting).
- Sort by score descending, return top k as Chunk objects with 
  `bm25_score` populated.

Add a private method `_rrf_merge(vector_results, bm25_results, k=50)`:
- Reciprocal Rank Fusion with constant c=60 (standard).
- For each chunk that appears in either list, compute:
  `rrf_score = 1/(c + rank_vector) + 1/(c + rank_bm25)`
  where rank is 1-indexed, and a chunk missing from one list contributes 
  zero from that side.
- Return top k chunks ranked by rrf_score, with `rrf_score` populated.

**Stop here. Run this test:**
```python
r = Retriever()
vec = r._vector_search("What does order_status mean?", None, k=10)
bm = r._bm25_search("What does order_status mean?", None, k=10)
merged = r._rrf_merge(vec, bm, k=10)
print("VECTOR TOP 5:")
for c in vec[:5]: print(c.source, c.section)
print("BM25 TOP 5:")
for c in bm[:5]: print(c.source, c.section)
print("RRF MERGED TOP 5:")
for c in merged[:5]: print(c.source, c.section, round(c.rrf_score, 4))
```

This output is gold. It will show you the three different rankings side 
by side. Expect fact_orders.md to dominate the BM25 side (exact token 
match on "order_status") and possibly the merged side, even though 
vector alone may have ranked seller_compliance.md higher. **This is the 
hybrid search story in action.** Show me the output.

---

### Part C: Cross-encoder reranking + public `retrieve()`

Load cross-encoder at `__init__`:
```python
from sentence_transformers import CrossEncoder
self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
```

First run downloads ~80MB.

Add `_rerank(query, chunks, top_k)`:
- For each chunk, build a `(query, chunk.content)` pair.
- Score all pairs with `self.reranker.predict(pairs)`.
- Sort chunks by reranker score descending.
- Return top_k with `reranker_score` populated.

Wire up the public `retrieve()`:
```python
def retrieve(self, query, top_k=5, doc_type=None):
    vec = self._vector_search(query, doc_type, k=50)
    bm = self._bm25_search(query, doc_type, k=50)
    merged = self._rrf_merge(vec, bm, k=50)
    final = self._rerank(query, merged, top_k=top_k)
    return final
```

**Stop here. Run this test:**
```python
r = Retriever()
results = r.retrieve("What does order_status mean?", top_k=5)
for c in results:
    print(c.source, c.section, round(c.reranker_score, 3))
```

Show me the output. Now we have the full pipeline.

---

## Checkpoint test: `app/rag/tests/test_stage4.py`

After Part C is verified, build a pytest test file with 5 hand-picked 
queries and expected source documents. The test asserts that the 
expected source appears in the top 3 results.

```python
import pytest
from app.rag.retriever import Retriever

@pytest.fixture(scope="module")
def retriever():
    return Retriever()

TEST_CASES = [
    {
        "query": "What does order_status mean?",
        "expected_source": "fact_orders.md",
        "doc_type": None,
    },
    {
        "query": "How does the payment fan-out happen?",
        "expected_source": "fact_order_payments.md",
        "doc_type": None,
    },
    {
        "query": "What is the difference between customer_id and customer_unique_id?",
        "expected_source": "dim_customers.md",
        "doc_type": None,
    },
    {
        "query": "What are the rules for seller compliance?",
        "expected_source": "seller_compliance.md",
        "doc_type": "policy",
    },
    {
        "query": "What products are in the bed_bath_table category?",
        "expected_source": "category_home_comfort.md",
        "doc_type": "category_def",
    },
]

@pytest.mark.parametrize("case", TEST_CASES)
def test_retrieval_top3(retriever, case):
    results = retriever.retrieve(
        query=case["query"],
        top_k=3,
        doc_type=case["doc_type"],
    )
    sources = [c.source for c in results]
    assert case["expected_source"] in sources, (
        f"Expected {case['expected_source']} in top 3 for query "
        f"'{case['query']}', got {sources}"
    )
```

Run with: `python -m pytest app/rag/tests/test_stage4.py -v`

If all 5 pass, Stage 4 checkpoint is passed. If any fail, surface the 
failure with the actual top 3 sources so we can decide if it's a real 
retrieval problem or a test case that needs adjustment.

---

## Constraints across all parts
- One file: `app/rag/retriever.py`. Don't split prematurely.
- Type hints on every function.
- Pydantic for Chunk model.
- `stdlib logging` for non-validation output.
- Reuse the same DB connection pattern as embed.py (SQLAlchemy + dotenv).
- BM25 corpus loaded once at init. Do not rebuild per query.
- Cross-encoder model loaded once at init. Do not reload per query.

## What NOT to do
- Do NOT add query rewriting, HyDE, or semantic chunking. Deferred per 
  CLAUDE.md Stage 4 locked scope.
- Do NOT cache query results. Premature optimization.
- Do NOT add async support. Synchronous is fine for this stage.
- Do NOT abstract the retrieval into a base class or strategy pattern. 
  One concrete class is enough.

## After completion
Show me:
1. The output from each of the three stop points (Parts A, B, C).
2. The pytest output from the checkpoint test.
3. Any failures with the actual retrieved sources so we can decide if 
   the test or the retriever needs adjustment.

Stop after the test run. Do not start Stage 5.