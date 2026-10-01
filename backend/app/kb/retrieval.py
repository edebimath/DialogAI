"""Semantic search over knowledge bases with pgvector (cosine distance, HNSW index)."""

import time

from pydantic import BaseModel
from sqlalchemy import func, or_, select, text

from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models import KBChunk, KBDocument
from app.kb.embedder import get_embedder


class Hit(BaseModel):
    chunk_id: int
    kb_id: str
    document_id: str
    document: str  # file name, or the question of a question-answer entry
    kind: str = "file"
    tags: list[str] = []
    page: int | None
    score: float  # cosine similarity, 0..1
    text: str


class SearchResult(BaseModel):
    query: str
    hits: list[Hit]
    ms: int


async def search(
    kb_ids: list[str],
    query: str,
    top_k: int = 4,
    min_score: float | None = None,
    tags: list[str] | None = None,
) -> SearchResult:
    """tags: the caller's tags (normalized). None = no filtering; otherwise untagged entries and
    entries sharing a tag with the caller (an empty list leaves only untagged entries)."""
    started = time.perf_counter()
    min_score = settings.kb_min_score if min_score is None else min_score
    if not kb_ids or not query.strip():
        return SearchResult(query=query, hits=[], ms=0)
    [vector] = await get_embedder().embed([query])
    distance = KBChunk.embedding.cosine_distance(vector)
    stmt = (
        select(KBChunk, KBDocument.filename, KBDocument.kind, distance.label("distance"))
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBChunk.kb_id.in_(kb_ids))
        .order_by(distance)
        .limit(top_k)
    )
    if tags is not None:
        visible = func.cardinality(KBChunk.tags) == 0
        stmt = stmt.where(or_(visible, KBChunk.tags.overlap(tags)) if tags else visible)
    async with SessionLocal() as db:
        if tags is not None:
            # A filtered HNSW scan otherwise stops at ef_search candidates and can come back short.
            await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        rows = (await db.execute(stmt)).all()
    # relaxed_order may return candidates slightly out of order.
    rows.sort(key=lambda r: r.distance)
    hits = [
        Hit(
            chunk_id=c.id,
            kb_id=c.kb_id,
            document_id=c.document_id,
            document=filename,
            kind=kind,
            tags=list(c.tags or []),
            page=c.page,
            score=round(1 - d, 3),
            text=c.text,
        )
        for c, filename, kind, d in rows
        if 1 - d >= min_score
    ]
    return SearchResult(query=query, hits=hits, ms=round((time.perf_counter() - started) * 1000))
