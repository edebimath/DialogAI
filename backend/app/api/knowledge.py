import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, Editor
from app.api.schemas import (
    ChunkOut,
    ChunkUpdate,
    DocumentOut,
    EntryUpdate,
    KBCreate,
    KBDetail,
    KBOut,
    KBUpdate,
    QAIn,
    SearchIn,
)
from app.db.models import KBChunk, KBDocument, KnowledgeBase, now
from app.kb import entries, ingest
from app.kb.parsing import SUPPORTED
from app.kb.retrieval import SearchResult, search
from app.api.tags import defined_tags
from app.kb.tags import normalize_tags

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 20


async def get_kb(db: AsyncSession, kb_id: str) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilgi tabanı bulunamadı.")
    return kb


async def kb_ids(db: AsyncSession) -> set[str]:
    return set((await db.scalars(select(KnowledgeBase.id))).all())


async def tagged_kb_ids(db: AsyncSession) -> set[str]:
    """Knowledge bases with at least one tagged entry; flows using them should say whose tags apply."""
    return set((await db.scalars(select(KBDocument.kb_id).where(func.cardinality(KBDocument.tags) > 0).distinct())).all())


async def get_entry(db: AsyncSession, kb_id: str, document_id: str) -> KBDocument:
    doc = await db.get(KBDocument, document_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Girdi bulunamadı.")
    return doc


async def get_chunk(db: AsyncSession, kb_id: str, chunk_id: int) -> KBChunk:
    chunk = await db.get(KBChunk, chunk_id)
    if chunk is None or chunk.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parça bulunamadı.")
    return chunk


async def entry_out(db: AsyncSession, doc: KBDocument) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.edited_chunks = await db.scalar(
        select(func.count(KBChunk.id)).where(KBChunk.document_id == doc.id, KBChunk.edited)
    )
    return out


def embedding_failed(e: entries.EmbeddingError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


async def kb_out(db: AsyncSession, kb: KnowledgeBase) -> KBOut:
    counts = (
        await db.execute(
            select(
                func.count(KBDocument.id),
                func.count(KBDocument.id).filter(KBDocument.status == "ready"),
                func.coalesce(func.sum(KBDocument.chunk_count), 0),
            ).where(KBDocument.kb_id == kb.id)
        )
    ).one()
    out = KBOut.model_validate(kb)
    out.document_count, out.ready_count, out.chunk_count = counts
    return out


@router.get("", response_model=list[KBOut])
async def list_kbs(db: DB, _: CurrentUser):
    rows = (await db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.name))).all()
    return [await kb_out(db, kb) for kb in rows]


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
async def create_kb(body: KBCreate, db: DB, user: Editor):
    kb = KnowledgeBase(name=body.name, description=body.description, created_by=user.id)
    db.add(kb)
    await db.commit()
    return await kb_out(db, kb)


@router.get("/{kb_id}", response_model=KBDetail)
async def read_kb(kb_id: str, db: DB, _: CurrentUser):
    kb = await get_kb(db, kb_id)
    docs = (
        await db.scalars(select(KBDocument).where(KBDocument.kb_id == kb.id).order_by(KBDocument.created_at.desc()))
    ).all()
    edited = dict(
        (
            await db.execute(
                select(KBChunk.document_id, func.count(KBChunk.id))
                .where(KBChunk.kb_id == kb.id, KBChunk.edited)
                .group_by(KBChunk.document_id)
            )
        ).all()
    )
    documents = []
    for d in docs:
        out = DocumentOut.model_validate(d)
        out.edited_chunks = edited.get(d.id, 0)
        documents.append(out)
    return KBDetail(**(await kb_out(db, kb)).model_dump(), documents=documents)


@router.patch("/{kb_id}", response_model=KBOut)
async def update_kb(kb_id: str, body: KBUpdate, db: DB, _: Editor):
    kb = await get_kb(db, kb_id)
    if body.name is not None:
        kb.name = body.name
    if body.description is not None:
        kb.description = body.description
    await db.commit()
    return await kb_out(db, kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(kb_id: str, db: DB, _: Editor):
    await db.delete(await get_kb(db, kb_id))
    await db.commit()
    shutil.rmtree(ingest.kb_dir(kb_id), ignore_errors=True)


@router.post("/{kb_id}/documents", response_model=list[DocumentOut], status_code=status.HTTP_201_CREATED)
async def upload_documents(kb_id: str, files: list[UploadFile], db: DB, user: Editor):
    kb = await get_kb(db, kb_id)
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Tek seferde en fazla {MAX_FILES_PER_UPLOAD} dosya yüklenebilir.")
    for f in files:
        # Checked before reading, so an oversized upload is never held in memory.
        if f.size is not None and f.size > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{f.filename}' 25 MB sınırını aşıyor.")
        if Path(f.filename or "").suffix.lower() not in SUPPORTED:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"'{f.filename}' desteklenmiyor. Desteklenen türler: PDF, DOCX, TXT, MD.",
            )
    directory = ingest.kb_dir(kb.id)
    directory.mkdir(parents=True, exist_ok=True)
    created: list[KBDocument] = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{f.filename}' 25 MB sınırını aşıyor.")
        doc = KBDocument(
            kb_id=kb.id,
            kind="file",
            tags=[],
            filename=Path(f.filename).name,
            content_type=f.content_type or "",
            size=len(data),
            path="",
            created_by=user.id,
        )
        db.add(doc)
        await db.flush()
        path = directory / f"{doc.id}{Path(f.filename).suffix.lower()}"
        path.write_bytes(data)
        doc.path = str(path)
        created.append(doc)
    kb.updated_at = now()
    await db.commit()
    for doc in created:
        ingest.enqueue(doc.id)
    return [DocumentOut.model_validate(d) for d in created]


@router.post("/{kb_id}/qa", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_qa(kb_id: str, body: QAIn, db: DB, user: Editor):
    """A question-answer entry typed in by hand; searchable as soon as it is saved."""
    kb = await get_kb(db, kb_id)
    doc = KBDocument(
        kb_id=kb.id,
        kind="qa",
        question=body.question.strip(),
        answer=body.answer.strip(),
        tags=await defined_tags(db, body.tags),
        filename="",
        path="",
        size=0,
        created_by=user.id,
    )
    db.add(doc)
    await db.flush()
    try:
        await entries.save_qa(db, doc)
    except entries.EmbeddingError as e:
        raise embedding_failed(e) from e
    kb.updated_at = now()
    await db.commit()
    return await entry_out(db, doc)


@router.patch("/{kb_id}/documents/{document_id}", response_model=DocumentOut)
async def update_entry(kb_id: str, document_id: str, body: EntryUpdate, db: DB, _: Editor):
    doc = await get_entry(db, kb_id, document_id)
    if body.tags is not None:
        await entries.set_tags(db, doc, await defined_tags(db, body.tags))
    if doc.kind == "qa" and (body.question is not None or body.answer is not None):
        doc.question = (body.question or doc.question or "").strip()
        doc.answer = (body.answer or doc.answer or "").strip()
        try:
            await entries.save_qa(db, doc)
        except entries.EmbeddingError as e:
            raise embedding_failed(e) from e
    doc.updated_at = now()
    (await get_kb(db, kb_id)).updated_at = now()
    await db.commit()
    return await entry_out(db, doc)


@router.get("/{kb_id}/documents/{document_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(kb_id: str, document_id: str, db: DB, _: CurrentUser):
    doc = await get_entry(db, kb_id, document_id)
    return (await db.scalars(select(KBChunk).where(KBChunk.document_id == doc.id).order_by(KBChunk.ordinal))).all()


@router.patch("/{kb_id}/chunks/{chunk_id}", response_model=ChunkOut)
async def update_chunk(kb_id: str, chunk_id: int, body: ChunkUpdate, db: DB, _: Editor):
    """Fix a chunk of a file by hand; it is embedded again right away."""
    chunk = await get_chunk(db, kb_id, chunk_id)
    doc = await db.get(KBDocument, chunk.document_id)
    if doc.kind == "qa":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Soru-cevap girdisini soru ve cevabından düzenleyin.")
    try:
        await entries.edit_chunk(db, chunk, body.text.strip())
    except entries.EmbeddingError as e:
        raise embedding_failed(e) from e
    doc.updated_at = now()
    await db.commit()
    return chunk


@router.delete("/{kb_id}/chunks/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chunk(kb_id: str, chunk_id: int, db: DB, _: Editor):
    chunk = await get_chunk(db, kb_id, chunk_id)
    await entries.delete_chunk(db, chunk)
    await db.commit()


@router.delete("/{kb_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(kb_id: str, document_id: str, db: DB, _: Editor):
    doc = await get_entry(db, kb_id, document_id)
    if doc.path:
        Path(doc.path).unlink(missing_ok=True)
    await db.delete(doc)
    (await get_kb(db, kb_id)).updated_at = now()
    await db.commit()


@router.post("/{kb_id}/documents/{document_id}/reindex", response_model=DocumentOut)
async def reindex_document(kb_id: str, document_id: str, db: DB, _: Editor):
    """Process the file again; chunks edited by hand are replaced."""
    doc = await get_entry(db, kb_id, document_id)
    doc.status, doc.error = "pending", None
    await db.commit()
    ingest.enqueue(doc.id)
    return await entry_out(db, doc)


@router.post("/{kb_id}/search", response_model=SearchResult)
async def search_kb(kb_id: str, body: SearchIn, db: DB, _: CurrentUser):
    """Try a question against the knowledge base, as the agent would."""
    await get_kb(db, kb_id)
    tags = None if body.tags is None else normalize_tags(body.tags)
    return await search([kb_id], body.query, body.top_k, min_score=0, tags=tags)

