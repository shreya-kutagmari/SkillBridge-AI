"""
utils/retrieval.py
-------------------
RAG retrieval: find the most relevant resume chunks for a query.

Uses cosine similarity between query embedding and stored chunk embeddings.
Falls back to simple keyword matching (TF-style overlap) when embeddings
are not available (no watsonx.ai credentials, or chunks stored without embeddings).

Public API
----------
retrieve_chunks(query, user_id, conn, top_k=3) -> list[str]
    Returns up to *top_k* most relevant chunk texts for *query*.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

from agents.ai_client import embed_texts, is_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_score(query: str, chunk: str) -> float:
    """
    Simple keyword overlap score (0.0–1.0) as a fallback when embeddings
    are unavailable.
    """
    query_tokens = set(query.lower().split())
    chunk_tokens = set(chunk.lower().split())
    if not query_tokens:
        return 0.0
    return len(query_tokens & chunk_tokens) / len(query_tokens)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_chunks(
    query: str,
    user_id: int,
    conn: sqlite3.Connection,
    top_k: int = 3,
) -> list[str]:
    """
    Return up to *top_k* most relevant resume chunk texts for *query*.

    Strategy:
    1. Fetch all chunks for *user_id* from the DB.
    2. If chunks have embeddings AND watsonx.ai is available → embed query,
       rank by cosine similarity.
    3. Otherwise → rank by keyword overlap (graceful degradation).

    Parameters
    ----------
    query   : search string (e.g. user's career question)
    user_id : logged-in user's id
    conn    : open sqlite3 connection
    top_k   : maximum number of chunks to return (default 3)

    Returns
    -------
    list[str] — chunk texts, best first; empty list if no chunks found
    """
    rows = conn.execute(
        "SELECT chunk_text, embedding_json FROM resume_chunks "
        "WHERE user_id=? ORDER BY chunk_index",
        (user_id,),
    ).fetchall()

    if not rows:
        return []

    chunks_text = [row["chunk_text"] for row in rows]
    embeddings_raw = [row["embedding_json"] for row in rows]

    # Check whether stored embeddings are available
    stored_embeddings: list[list[float] | None] = [
        json.loads(e) if e else None for e in embeddings_raw
    ]
    has_embeddings = any(e is not None for e in stored_embeddings)

    # ── Path 1: vector similarity ─────────────────────────────────────────
    if has_embeddings and is_available():
        query_vecs = embed_texts([query])
        if query_vecs and len(query_vecs) == 1:
            q_vec = query_vecs[0]
            scored = []
            for text, emb in zip(chunks_text, stored_embeddings):
                if emb is not None:
                    score = _cosine_similarity(q_vec, emb)
                else:
                    score = _keyword_score(query, text)
                scored.append((score, text))
            scored.sort(key=lambda x: x[0], reverse=True)
            logger.debug("retrieve_chunks: vector path, top score=%.3f", scored[0][0] if scored else 0)
            return [text for _, text in scored[:top_k]]

    # ── Path 2: keyword fallback ─────────────────────────────────────────
    logger.debug("retrieve_chunks: keyword fallback for user %d", user_id)
    scored = [(  _keyword_score(query, text), text) for text in chunks_text]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]
