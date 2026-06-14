"""
Stage 4 hybrid retriever: pgvector cosine + BM25, merged via RRF, reranked
via cross-encoder.

Built in three parts (see RETRIEVER_BRIEF.md):
  Part A: vector search with metadata filtering
  Part B: BM25 + Reciprocal Rank Fusion
  Part C: cross-encoder rerank + public retrieve()
"""
import logging
import os
import re

import sqlalchemy as sa
from dotenv import load_dotenv
from pydantic import BaseModel
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_C = 60

# Boilerplate section titles in the corpus ("What it does NOT cover", "What
# this table CANNOT answer") match query words like "what"/"does" and flood
# BM25 with chunks that lack the discriminating identifier. Dropping common
# English words leaves identifier tokens (order_status, customer_unique_id)
# to drive BM25 scoring.
STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "between", "by", "did", "do",
    "does", "for", "from", "how", "in", "is", "it", "its", "mean", "means",
    "of", "on", "or", "that", "the", "this", "to", "what", "with",
})


def _tokenize(text_in: str) -> list[str]:
    tokens = re.sub(r"[^a-z0-9_\s]", " ", text_in.lower()).split()
    return [t for t in tokens if t not in STOPWORDS]


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


def _to_pgvector(embedding: list[float]) -> str:
    return "[" + ",".join(map(str, embedding)) + "]"


class Retriever:
    def __init__(self) -> None:
        load_dotenv()
        self.engine = sa.create_engine(os.environ["DATABASE_URL"])
        log.info("Loading embedding model: %s", EMBED_MODEL)
        self.embedder = SentenceTransformer(EMBED_MODEL)
        log.info("Loading cross-encoder: %s", RERANKER_MODEL)
        self.reranker = CrossEncoder(RERANKER_MODEL)
        self._build_bm25_index()

    def _build_bm25_index(self) -> None:
        """Load all chunks into memory once and build the BM25 index."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, source, doc_type, doc_title, section, content "
                    "FROM doc_chunks"
                )
            ).fetchall()
        # Keep full chunk metadata so _bm25_search can build Chunk objects
        # without a per-query DB round-trip.
        self._corpus: list[Chunk] = [
            Chunk(
                chunk_id=str(r[0]),
                source=r[1],
                doc_type=r[2],
                doc_title=r[3],
                section=r[4],
                content=r[5],
            )
            for r in rows
        ]
        tokenized_corpus = [_tokenize(c.content) for c in self._corpus]
        self._bm25 = BM25Okapi(tokenized_corpus)
        log.info("BM25 index built over %d chunks", len(self._corpus))

    def _embed_query(self, query: str) -> list[float]:
        return self.embedder.encode([query])[0].tolist()

    def _vector_search(
        self,
        query: str,
        doc_type: str | None = None,
        k: int = 50,
    ) -> list[Chunk]:
        q_vec = _to_pgvector(self._embed_query(query))
        sql = text(
            """
            SELECT id, source, doc_type, doc_title, section, content,
                   embedding <=> CAST(:q AS vector) AS distance
            FROM doc_chunks
            WHERE (:dt IS NULL OR doc_type = :dt)
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :k
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"q": q_vec, "dt": doc_type, "k": k}).fetchall()

        return [
            Chunk(
                chunk_id=str(row[0]),
                source=row[1],
                doc_type=row[2],
                doc_title=row[3],
                section=row[4],
                content=row[5],
                vector_distance=float(row[6]),
            )
            for row in rows
        ]

    def _bm25_search(
        self,
        query: str,
        doc_type: str | None = None,
        k: int = 50,
    ) -> list[Chunk]:
        scores = self._bm25.get_scores(_tokenize(query))
        scored = [
            (chunk, float(score))
            for chunk, score in zip(self._corpus, scores)
            if doc_type is None or chunk.doc_type == doc_type
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        results: list[Chunk] = []
        for chunk, score in scored[:k]:
            results.append(chunk.model_copy(update={"bm25_score": score}))
        return results

    def _rrf_merge(
        self,
        vector_results: list[Chunk],
        bm25_results: list[Chunk],
        k: int = 50,
    ) -> list[Chunk]:
        vector_rank = {c.chunk_id: i + 1 for i, c in enumerate(vector_results)}
        bm25_rank = {c.chunk_id: i + 1 for i, c in enumerate(bm25_results)}
        by_id: dict[str, Chunk] = {c.chunk_id: c for c in vector_results}
        for c in bm25_results:
            by_id.setdefault(c.chunk_id, c)

        merged: list[Chunk] = []
        for chunk_id, base in by_id.items():
            score = 0.0
            if chunk_id in vector_rank:
                score += 1.0 / (RRF_C + vector_rank[chunk_id])
            if chunk_id in bm25_rank:
                score += 1.0 / (RRF_C + bm25_rank[chunk_id])
            merged.append(base.model_copy(update={"rrf_score": score}))

        merged.sort(key=lambda c: c.rrf_score or 0.0, reverse=True)
        return merged[:k]

    def _rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        if not chunks:
            return []
        pairs = [(query, c.content) for c in chunks]
        scores = self.reranker.predict(pairs)
        rescored = [
            c.model_copy(update={"reranker_score": float(s)})
            for c, s in zip(chunks, scores)
        ]
        rescored.sort(key=lambda c: c.reranker_score or 0.0, reverse=True)
        return rescored[:top_k]

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[Chunk]:
        vec = self._vector_search(query, doc_type, k=50)
        bm = self._bm25_search(query, doc_type, k=50)
        merged = self._rrf_merge(vec, bm, k=50)
        final = self._rerank(query, merged, top_k=top_k)
        return final


if __name__ == "__main__":
    r = Retriever()
    results = r.retrieve("What does order_status mean?", top_k=5)
    for c in results:
        print(c.source, c.section, round(c.reranker_score, 3))
