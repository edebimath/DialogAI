"""Background indexing of uploaded documents: parse, chunk, embed, store.

One in-process worker handles documents in upload order; documents left pending or processing
by a restart are picked up again at startup.
"""

import asyncio
from pathlib import Path

from loguru import logger
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models import KBChunk, KBDocument, KnowledgeBase, now
from app.kb.embedder import get_embedder
from app.kb.entries import save_qa
from app.kb.parsing import ParseError, chunk, extract

# Created by start_worker: a queue is bound to the event loop that first uses it.
_queue: asyncio.Queue[str] | None = None
_worker: asyncio.Task | None = None


def kb_dir(kb_id: str) -> Path:
    return settings.data_dir / "kb" / kb_id


def enqueue(document_id: str) -> None:
    if _queue is None:
        raise RuntimeError("Indexing worker is not running")
    _queue.put_nowait(document_id)


async def index_document(document_id: str) -> None:
    async with SessionLocal() as db:
        doc = await db.get(KBDocument, document_id)
        if doc is None:
            return
        doc.status, doc.error = "processing", None
        await db.commit()
        try:
            if doc.kind == "qa":
                await save_qa(db, doc)
                await db.commit()
                return
            sections = await asyncio.to_thread(extract, Path(doc.path))
            pieces = chunk(sections)
            if not pieces:
                raise ParseError("Dosyada okunabilir metin bulunamadı (taranmış bir PDF olabilir).")
            vectors = await get_embedder().embed([p.text for p in pieces])
            await db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))
            db.add_all(
                KBChunk(
                    kb_id=doc.kb_id,
                    document_id=doc.id,
                    ordinal=i,
                    page=piece.page,
                    text=piece.text,
                    embedding=vector,
                    tags=list(doc.tags),
                )
                for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
            )
            doc.status, doc.chunk_count = "ready", len(pieces)
            logger.info(f"Indexed {doc.filename}: {len(pieces)} chunks")
        except Exception as e:
            await db.rollback()
            doc = await db.get(KBDocument, document_id)
            doc.status, doc.error = "failed", str(e) if isinstance(e, ParseError) else f"{type(e).__name__}: {e}"
            logger.warning(f"Indexing {doc.filename} failed: {e}")
        kb = await db.get(KnowledgeBase, doc.kb_id)
        if kb:
            kb.updated_at = now()
        await db.commit()


async def _run() -> None:
    while True:
        document_id = await _queue.get()
        try:
            await index_document(document_id)
        except Exception:
            logger.exception(f"Indexing worker failed on {document_id}")
        finally:
            _queue.task_done()


async def start_worker() -> None:
    global _worker, _queue
    _queue = asyncio.Queue()
    async with SessionLocal() as db:
        unfinished = await db.scalars(
            select(KBDocument.id)
            .where(KBDocument.status.in_(("pending", "processing")))
            .order_by(KBDocument.created_at)
        )
        for document_id in unfinished:
            enqueue(document_id)
    _worker = asyncio.create_task(_run())


async def stop_worker() -> None:
    if _worker:
        _worker.cancel()


async def wait_idle() -> None:
    """Tests: wait until every queued document is processed."""
    if _queue is not None:
        await _queue.join()
