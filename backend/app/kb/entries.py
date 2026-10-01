"""Hand-edited knowledge: question-answer entries, chunk edits and entry tags.

These are small and embedded right away (one embedding is ~30 ms), unlike files, which go
through the indexing worker.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KBChunk, KBDocument
from app.kb.embedder import get_embedder


class EmbeddingError(Exception):
    """The embedding model couldn't be reached; nothing was saved."""


def qa_text(question: str, answer: str) -> str:
    """What gets embedded and what the agent reads when the entry is found."""
    return f"Soru: {question.strip()}\nCevap: {answer.strip()}"


def qa_title(question: str) -> str:
    """Stands in for a file name wherever entries are listed (trace, search results)."""
    question = " ".join(question.split())
    return question if len(question) <= 120 else question[:117] + "…"


async def _embed(text: str) -> list[float]:
    try:
        [vector] = await get_embedder().embed([text])
    except Exception as e:
        raise EmbeddingError(f"Gömme modeline ulaşılamadı, kaydedilmedi: {e}") from e
    return vector


async def save_qa(db: AsyncSession, doc: KBDocument) -> None:
    """(Re)builds the single chunk of a question-answer entry. The caller commits."""
    text = qa_text(doc.question or "", doc.answer or "")
    vector = await _embed(text)
    doc.filename = qa_title(doc.question or "")
    await db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))
    db.add(KBChunk(kb_id=doc.kb_id, document_id=doc.id, ordinal=0, text=text, embedding=vector, tags=list(doc.tags)))
    doc.status, doc.error, doc.chunk_count = "ready", None, 1


async def set_tags(db: AsyncSession, doc: KBDocument, tags: list[str]) -> None:
    doc.tags = tags
    await db.execute(update(KBChunk).where(KBChunk.document_id == doc.id).values(tags=tags))


async def edit_chunk(db: AsyncSession, chunk: KBChunk, text: str) -> None:
    chunk.embedding = await _embed(text)
    chunk.text, chunk.edited = text, True


async def delete_chunk(db: AsyncSession, chunk: KBChunk) -> None:
    doc = await db.get(KBDocument, chunk.document_id)
    await db.delete(chunk)
    await db.flush()
    doc.chunk_count = await db.scalar(select(func.count(KBChunk.id)).where(KBChunk.document_id == doc.id))
