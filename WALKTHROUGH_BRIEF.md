# SemaFlow Stage 4 Walkthrough: Static HTML Site

## Goal
Build a multi-page static HTML site that visually walks through the 
SemaFlow Stage 4 RAG pipeline using real data from the build. The site 
will be opened locally in a browser (double-click) and is intended as 
a learning aid and a recording prop.

## Output location
`app/rag/walkthrough/`
- `index.html` (landing + nav)
- `01_corpus.html`
- `02_chunking.html`
- `03_embedding.html`
- `04_vector_search.html`
- `05_bm25.html`
- `06_rrf.html`
- `07_reranker.html`
- `08_full_pipeline.html`
- `style.css` (shared)
- `data/walkthrough_data.json` (precomputed)
- `precompute.py` (one-shot script that generates walkthrough_data.json)

## Tech constraints
- Static HTML, vanilla CSS, vanilla JS. No frameworks, no build step.
- One CSS file shared across pages.
- D3.js OR plain SVG for visualizations. Pick whichever is simpler per chart.
- No live model loading in the browser. All numbers are precomputed.
- No CDN dependencies that require internet. If using D3, vendor it 
  locally into the walkthrough folder.

## Precompute script (precompute.py)
Runs the retriever pipeline for ONE worked example query 
("What does order_status mean?") and serializes all intermediate 
results to walkthrough_data.json:

- Corpus stats: total docs, total chunks, breakdown by doc_type.
- All 147 chunks with full metadata.
- 2D projection of all 147 chunk embeddings via PCA (use sklearn). 
  Output (x, y) pairs labeled by doc_type and source.
- The example query, its embedding (full 384 dims for the embedding 
  page, first 20 dims for display).
- The 2D projection of the query embedding (project into the same PCA 
  space).
- Vector search top 10 with cosine distances.
- BM25 tokenization of the query (raw tokens, after stopword removal).
- BM25 top 10 with scores.
- RRF merged top 10 with rrf_score, vector rank, bm25 rank.
- Reranker top 5 with reranker scores.
- All ranking data joined to chunk metadata so the HTML pages can show 
  source, section, content preview, etc.

Save to walkthrough_data.json with sensible nesting:
{
  "corpus": {...},
  "query": "What does order_status mean?",
  "chunks": [...],
  "projection_2d": {...},
  "vector_results": [...],
  "bm25_results": [...],
  "bm25_tokens": [...],
  "rrf_results": [...],
  "reranker_results": [...]
}

## Page content (concise)

### index.html
- Title: "SemaFlow RAG: How It Actually Works"
- Subtitle: one sentence on the worked-example approach.
- Nav links to all 8 pages.
- One-paragraph summary of the stack: 147 chunks, all-MiniLM-L6-v2, 
  pgvector, BM25, RRF, cross-encoder.

### 01_corpus.html
- Tree view: 3 folders, document counts, click to expand.
- One example doc shown in raw form (fact_orders.md) with H2 sections 
  highlighted.
- Stats panel: 24 docs, ~150 chunks, breakdown by doc_type.

### 02_chunking.html
- Show fact_orders.md split into chunks visually: each chunk as a card 
  with metadata (source, doc_type, section, char_start, char_end, 
  token_count) and a content preview.
- Visual emphasis on the 32-token overlap: highlight the overlapping 
  text between adjacent chunks.
- Caption explaining: header-aware first, then fixed-size 256/32, 
  metadata attached at chunk time.

### 03_embedding.html
- Show one chunk → arrow → vector. Display the first 20 of the 384 
  dimensions as numbers.
- Visual: 2D PCA scatter plot of all 147 chunks, colored by doc_type 
  (data_dictionary blue, policy green, category_def orange).
- Caption explaining: same model embeds chunks and queries, 384 dims, 
  cosine distance measures direction not magnitude. Clusters visible in 
  the 2D projection show doc_type separation.

### 04_vector_search.html
- The example query "What does order_status mean?" embedded into the 
  same space. Show its 2D point on the projection.
- Highlight the 10 nearest neighbors with lines from the query point 
  to each.
- Table: top 10 with source, section, cosine distance.
- Caption explaining: the distances cluster tightly (0.515 to 0.55), 
  the right answer is in there but not winning. Vector search has 
  fuzzy boundaries.

### 05_bm25.html
- Show the query going through the tokenizer. Before stopword removal: 
  full token list. After stopword removal: ["order_status"].
- Show the same chunks but ranked by BM25. Table with top 10: source, 
  section, BM25 score.
- Side-by-side or below: contrast with the vector top 10.
- Caption: explain why the underscore-preserving tokenizer matters, 
  why stopword removal helps, and the length-normalization observation 
  (short policy chunks rank above the long defining chunk).

### 06_rrf.html
- Three columns: vector top 10, BM25 top 10, RRF merged top 10.
- For each chunk in RRF column, show its rank in vector and BM25, and 
  the resulting RRF score.
- Visual showing the RRF formula: rrf_score = 1/(60+rank_v) + 1/(60+rank_b)
- Caption: explain why we use ranks not scores (incomparable scales), 
  why c=60 is the standard choice.

### 07_reranker.html
- Top 10 from RRF go into the cross-encoder.
- Show the cross-encoder scoring each (query, chunk_content) pair.
- Output: top 5 after rerank, with reranker_score.
- Side-by-side with RRF top 5 to show the reordering.
- Caption: bi-encoder vs cross-encoder distinction. Why we don't 
  cross-encode all 147 (too expensive). The two-stage retrieve-then- 
  rerank pattern.

### 08_full_pipeline.html
- A single diagram showing the full flow: query in, embedding + 
  tokenization, vector + BM25 in parallel, RRF merge, cross-encoder, 
  top 5 out.
- Final top 5 displayed with full metadata and content previews.
- Closing paragraph on what each stage prevents.

## Visual style
- Clean, plain. White background, dark text, restrained color palette.
- One accent color for highlights (a deep blue or muted teal).
- Monospace for chunk content, code, scores.
- No animations beyond simple transitions.
- Mobile-readable but desktop-first (this is for explanation, not 
  consumption on phones).

## What NOT to do
- Do NOT make this look like a marketing site or a product demo.
- Do NOT add buzzwords like "revolutionary," "powerful," "state-of-the-art."
- Do NOT load models or run any ML in the browser. All precomputed.
- Do NOT add login, analytics, telemetry, or any external services.
- Do NOT add a chatbot interface. This is a walkthrough, not an app.
- Do NOT use Tailwind, React, Vue, or any framework. Plain HTML/CSS/JS.

## Validation
After building:
1. Open index.html in a browser. All 8 pages render.
2. Navigation works between pages.
3. Visualizations show real data from walkthrough_data.json.
4. Numbers match what the retriever actually produced today.
5. Spot-check one chunk's metadata against doc_chunks table in Postgres.

## Stop after
Generate the precompute script, run it, build all 9 HTML files, share 
the index.html path. Do NOT open Stage 5 or modify any retriever code.