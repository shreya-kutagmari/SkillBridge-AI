"""
utils/embeddings.py
--------------------
Resume chunking and embedding storage for RAG retrieval.

Splits resume text into overlapping sentence-level chunks, generates
watsonx.ai embeddings for each chunk, and stores them in the
`resume_chunks` table. Falls back gracefully (stores chunks without
embeddings) when watsonx.ai is not available.

Public API
----------
store_resume_chunks(user_id, filename, text, conn) -> int
    Chunks the text, embeds, stores in DB. Returns count of chunks stored.

delete_resume_chunks(user_id, conn)
    Removes all chunks for a user (call before re-uploading).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3

from agents.ai_client import embed_texts, is_available

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
_CHUNK_SIZE   = 5    # sentences per chunk
_CHUNK_OVERLAP = 2   # sentences overlapping between consecutive chunks


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using a simple regex."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _make_chunks(sentences: list[str], size: int, overlap: int) -> list[str]:
    """
    Produce overlapping chunks from a sentence list.

    Each chunk is *size* sentences; consecutive chunks overlap by *overlap*
    sentences. Falls back to the full text as one chunk if very short.
    """
    if not sentences:
        return []
    if len(sentences) <= size:
        return [" ".join(sentences)]

    chunks: list[str] = []
    step = max(1, size - overlap)
    for i in range(0, len(sentences), step):
        chunk_sentences = sentences[i : i + size]
        if chunk_sentences:
            chunks.append(" ".join(chunk_sentences))
    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def store_resume_chunks(
    user_id: int,
    filename: str,
    text: str,
    conn: sqlite3.Connection,
) -> int:
    """
    Chunk *text*, optionally embed, and insert into `resume_chunks`.

    Deletes any existing chunks for *user_id* before inserting new ones
    so re-uploads replace the old data cleanly.

    Parameters
    ----------
    user_id  : logged-in user's id
    filename : secure filename of the uploaded file
    text     : full extracted resume text
    conn     : open sqlite3 connection (caller manages commit/close)

    Returns
    -------
    int — number of chunks stored
    """
    # Always clean up old chunks for this user first
    delete_resume_chunks(user_id, conn)

    sentences = _split_into_sentences(text)
    chunks = _make_chunks(sentences, _CHUNK_SIZE, _CHUNK_OVERLAP)

    if not chunks:
        logger.warning("store_resume_chunks: no chunks produced for user %d", user_id)
        return 0

    # Try to embed all chunks at once
    embeddings: list[list[float]] | None = None
    if is_available():
        embeddings = embed_texts(chunks)
        if embeddings is None:
            logger.warning(
                "store_resume_chunks: embedding failed for user %d — storing without embeddings",
                user_id,
            )

    rows = []
    for idx, chunk_text in enumerate(chunks):
        emb_json: str | None = None
        if embeddings and idx < len(embeddings):
            emb_json = json.dumps(embeddings[idx])
        rows.append((user_id, filename, idx, chunk_text, emb_json))

    conn.executemany(
        "INSERT INTO resume_chunks"
        "(user_id, resume_filename, chunk_index, chunk_text, embedding_json)"
        " VALUES (?,?,?,?,?)",
        rows,
    )
    logger.info(
        "store_resume_chunks: stored %d chunks for user %d (embedded=%s)",
        len(rows),
        user_id,
        embeddings is not None,
    )
    return len(rows)


def delete_resume_chunks(user_id: int, conn: sqlite3.Connection) -> None:
    """Remove all resume chunks for *user_id*."""
    conn.execute("DELETE FROM resume_chunks WHERE user_id=?", (user_id,))
