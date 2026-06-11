"""
One-shot precompute for the Stage 4 walkthrough site.

Runs the real retriever pipeline for a single worked-example query and
serializes every intermediate result to data/walkthrough_data.json. The HTML
pages read that JSON; no model ever loads in the browser.

Run from project root:
    .venv/bin/python app/rag/walkthrough/precompute.py

Reuses app/rag/retriever.py unchanged: the same vector search, BM25,
RRF merge, and cross-encoder that the checkpoint tests exercise.
"""
import json
import logging
import os
import re
import sys
from pathlib import Path

import numpy as np
import sqlalchemy as sa
from dotenv import load_dotenv
from sklearn.decomposition import PCA
from sqlalchemy import text

# Import the production retriever without copying any of its logic.
RAG_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAG_DIR))
import retriever as rt  # noqa: E402  (path set above)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("precompute")

QUERY = "What does order_status mean?"
EXAMPLE_DOC = "fact_orders.md"
OUT_PATH = Path(__file__).resolve().parent / "data" / "walkthrough_data.json"
PREVIEW_CHARS = 180


def preview(content: str) -> str:
    flat = " ".join(content.split())
    return flat[:PREVIEW_CHARS] + ("..." if len(flat) > PREVIEW_CHARS else "")


def fetch_all_chunks(engine: sa.Engine) -> list[dict]:
    """Pull every chunk row plus its embedding (as text) from doc_chunks."""
    sql = text(
        """
        SELECT id, source, doc_type, doc_title, section, chunk_index,
               char_start, char_end, token_count, content, embedding::text
        FROM doc_chunks
        ORDER BY source, chunk_index
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()

    chunks = []
    for r in rows:
        emb = [float(x) for x in r[10].strip("[]").split(",")]
        chunks.append(
            {
                "chunk_id": str(r[0]),
                "source": r[1],
                "doc_type": r[2],
                "doc_title": r[3],
                "section": r[4],
                "chunk_index": r[5],
                "char_start": r[6],
                "char_end": r[7],
                "token_count": r[8],
                "content": r[9],
                "_embedding": emb,
            }
        )
    log.info("Fetched %d chunks from doc_chunks", len(chunks))
    return chunks


def corpus_stats(chunks: list[dict]) -> dict:
    docs_by_type: dict[str, set[str]] = {}
    chunks_by_type: dict[str, int] = {}
    for c in chunks:
        dt = c["doc_type"]
        docs_by_type.setdefault(dt, set()).add(c["source"])
        chunks_by_type[dt] = chunks_by_type.get(dt, 0) + 1

    folders = []
    # Map doc_type back to the on-disk folder name for the tree view.
    folder_name = {
        "data_dictionary": "data_dictionary/",
        "policy": "policy/",
        "category_def": "categories/",
    }
    for dt in sorted(docs_by_type):
        folders.append(
            {
                "folder": folder_name.get(dt, dt),
                "doc_type": dt,
                "doc_count": len(docs_by_type[dt]),
                "chunk_count": chunks_by_type[dt],
                "files": sorted(docs_by_type[dt]),
            }
        )

    return {
        "total_docs": sum(len(v) for v in docs_by_type.values()),
        "total_chunks": len(chunks),
        "docs_by_type": {k: len(v) for k, v in sorted(docs_by_type.items())},
        "chunks_by_type": dict(sorted(chunks_by_type.items())),
        "folders": folders,
    }


def example_doc_block(chunks: list[dict]) -> dict:
    """Raw markdown of the example doc plus its H2 section offsets."""
    path = Path("app/corpus/docs/data_dictionary") / EXAMPLE_DOC
    raw = path.read_text(encoding="utf-8")
    sections = []
    for m in re.finditer(r"^## (.+)$", raw, re.MULTILINE):
        sections.append({"name": m.group(1).strip(), "char_start": m.start()})
    doc_chunks = [
        {k: v for k, v in c.items() if k != "_embedding"}
        for c in chunks
        if c["source"] == EXAMPLE_DOC
    ]
    return {
        "source": EXAMPLE_DOC,
        "doc_type": doc_chunks[0]["doc_type"] if doc_chunks else "data_dictionary",
        "content": raw,
        "sections": sections,
        "chunks": doc_chunks,
    }


def projection_2d(chunks: list[dict], query_emb: list[float]) -> dict:
    """Fit PCA on the 147 chunk embeddings, project chunks and the query."""
    matrix = np.array([c["_embedding"] for c in chunks])
    pca = PCA(n_components=2, random_state=0)
    coords = pca.fit_transform(matrix)
    q_xy = pca.transform(np.array([query_emb]))[0]

    points = [
        {
            "chunk_id": c["chunk_id"],
            "source": c["source"],
            "doc_type": c["doc_type"],
            "x": round(float(coords[i][0]), 4),
            "y": round(float(coords[i][1]), 4),
        }
        for i, c in enumerate(chunks)
    ]
    return {
        "explained_variance": [round(float(v), 4) for v in pca.explained_variance_ratio_],
        "chunks": points,
        "query": {"x": round(float(q_xy[0]), 4), "y": round(float(q_xy[1]), 4)},
    }


def slim(chunk: rt.Chunk, extra: dict | None = None) -> dict:
    out = {
        "chunk_id": chunk.chunk_id,
        "source": chunk.source,
        "doc_type": chunk.doc_type,
        "section": chunk.section,
        "preview": preview(chunk.content),
    }
    if extra:
        out.update(extra)
    return out


def main() -> None:
    load_dotenv()
    engine = sa.create_engine(os.environ["DATABASE_URL"])

    chunks = fetch_all_chunks(engine)

    log.info("Instantiating retriever (loads embedder + cross-encoder)...")
    r = rt.Retriever()

    # --- query embedding ---
    query_emb = r._embed_query(QUERY)

    # --- the four pipeline stages, exactly as retrieve() runs them ---
    vec50 = r._vector_search(QUERY, None, k=50)
    bm50 = r._bm25_search(QUERY, None, k=50)
    merged = r._rrf_merge(vec50, bm50, k=50)
    reranked = r._rerank(QUERY, merged, top_k=5)

    vec_rank = {c.chunk_id: i + 1 for i, c in enumerate(vec50)}
    bm_rank = {c.chunk_id: i + 1 for i, c in enumerate(bm50)}
    rrf_rank = {c.chunk_id: i + 1 for i, c in enumerate(merged)}

    # --- tokenization, before and after stopword removal ---
    raw_tokens = re.sub(r"[^a-z0-9_\s]", " ", QUERY.lower()).split()
    filtered_tokens = rt._tokenize(QUERY)

    vector_results = [
        slim(c, {"vector_distance": round(c.vector_distance, 4)})
        for c in vec50[:10]
    ]
    bm25_results = [
        slim(c, {"bm25_score": round(c.bm25_score, 4)}) for c in bm50[:10]
    ]
    rrf_results = [
        slim(
            c,
            {
                "rrf_score": round(c.rrf_score, 6),
                "vector_rank": vec_rank.get(c.chunk_id),
                "bm25_rank": bm_rank.get(c.chunk_id),
            },
        )
        for c in merged[:10]
    ]
    reranker_results = [
        slim(
            c,
            {
                "reranker_score": round(c.reranker_score, 4),
                "rrf_rank": rrf_rank.get(c.chunk_id),
                "content": c.content,
            },
        )
        for c in reranked
    ]
    # RRF top 5 for the side-by-side comparison on the reranker page.
    rrf_top5 = [
        slim(c, {"rrf_score": round(c.rrf_score, 6), "rrf_rank": i + 1})
        for i, c in enumerate(merged[:5])
    ]

    data = {
        "query": QUERY,
        "corpus": corpus_stats(chunks),
        "example_doc": example_doc_block(chunks),
        "chunks": [
            {k: v for k, v in c.items() if k != "_embedding"} for c in chunks
        ],
        "query_embedding_preview": [round(float(x), 5) for x in query_emb[:20]],
        "query_embedding_dims": len(query_emb),
        "projection_2d": projection_2d(chunks, query_emb),
        "bm25_tokens": {"raw": raw_tokens, "filtered": filtered_tokens},
        "vector_results": vector_results,
        "bm25_results": bm25_results,
        "rrf_results": rrf_results,
        "rrf_top5": rrf_top5,
        "reranker_results": reranker_results,
        "params": {"rrf_c": rt.RRF_C, "chunk_size": 256, "overlap": 32},
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    OUT_PATH.write_text(payload, encoding="utf-8")
    log.info("Wrote %s", OUT_PATH)

    # Browsers block fetch() of a file:// JSON, so the pages can't load the
    # JSON directly when opened by double-click. Emit a JS wrapper that assigns
    # the same payload to a global the pages read with a plain <script> tag.
    js_path = OUT_PATH.with_suffix(".js")
    js_path.write_text(
        "// Generated by precompute.py. Do not edit by hand.\n"
        "window.WALKTHROUGH_DATA = " + payload + ";\n",
        encoding="utf-8",
    )
    log.info("Wrote %s", js_path)

    # Console summary for verification.
    print("\n=== precompute summary ===")
    print(f"query:           {QUERY}")
    print(f"total docs:      {data['corpus']['total_docs']}")
    print(f"total chunks:    {data['corpus']['total_chunks']}")
    print(f"chunks by type:  {data['corpus']['chunks_by_type']}")
    print(f"PCA variance:    {data['projection_2d']['explained_variance']}")
    print(f"raw tokens:      {raw_tokens}")
    print(f"filtered tokens: {filtered_tokens}")
    print("\nvector top 5 (distance):")
    for c in vector_results[:5]:
        print(f"  {c['vector_distance']:.4f}  {c['source']} / {c['section']}")
    print("\nbm25 top 5 (score):")
    for c in bm25_results[:5]:
        print(f"  {c['bm25_score']:.4f}  {c['source']} / {c['section']}")
    print("\nrrf top 5 (score, v-rank, b-rank):")
    for c in rrf_results[:5]:
        print(f"  {c['rrf_score']:.6f}  v={c['vector_rank']} b={c['bm25_rank']}  {c['source']} / {c['section']}")
    print("\nreranker top 5 (score):")
    for c in reranker_results:
        print(f"  {c['reranker_score']:.4f}  (rrf#{c['rrf_rank']})  {c['source']} / {c['section']}")


if __name__ == "__main__":
    main()
