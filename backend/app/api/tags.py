"""Tags defined on the tags screen: which callers knowledge-base entries are for."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, Editor
from app.api.schemas import TagIn, TagOut, TagUpdate
from app.db.models import KBChunk, KBDocument, KBTag, now
from app.kb.tags import normalize_tag, normalize_tags

router = APIRouter(prefix="/api/tags", tags=["tags"])


async def usage(db: AsyncSession) -> dict[str, int]:
    """Entries per tag name."""
    tag = func.unnest(KBDocument.tags).label("tag")
    sub = select(tag).subquery()
    rows = await db.execute(select(sub.c.tag, func.count()).group_by(sub.c.tag))
    return dict(rows.all())


async def get_tag(db: AsyncSession, tag_id: str) -> KBTag:
    tag = await db.get(KBTag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Etiket bulunamadı.")
    return tag


async def check_name(db: AsyncSession, name: str, own_id: str | None = None) -> str:
    normalized = normalize_tag(name)
    if not normalized:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Etiket adı boş olamaz.")
    if "," in normalized:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Etiket adında virgül kullanılamaz.")
    existing = await db.scalar(select(KBTag).where(KBTag.name == normalized))
    if existing is not None and existing.id != own_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{normalized}' etiketi zaten var.")
    return normalized


async def defined_tags(db: AsyncSession, names: list[str]) -> list[str]:
    """Normalized names, all of them defined; raises 400 naming the first undefined one."""
    names = normalize_tags(names)
    known = set((await db.scalars(select(KBTag.name).where(KBTag.name.in_(names)))).all())
    for name in names:
        if name not in known:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{name}' tanımlı bir etiket değil. Önce Etiketler ekranından oluşturun.")
    return names


def tag_out(tag: KBTag, counts: dict[str, int]) -> TagOut:
    out = TagOut.model_validate(tag)
    out.entry_count = counts.get(tag.name, 0)
    return out


@router.get("", response_model=list[TagOut])
async def list_tags(db: DB, _: CurrentUser):
    counts = await usage(db)
    tags = (await db.scalars(select(KBTag).order_by(KBTag.name))).all()
    return [tag_out(t, counts) for t in tags]


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(body: TagIn, db: DB, _: Editor):
    tag = KBTag(name=await check_name(db, body.name), description=body.description.strip(), color=body.color)
    db.add(tag)
    await db.commit()
    return tag_out(tag, {})


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(tag_id: str, body: TagUpdate, db: DB, _: Editor):
    """Renaming rewrites the tag on every entry that carries it."""
    tag = await get_tag(db, tag_id)
    if body.name is not None:
        new = await check_name(db, body.name, own_id=tag.id)
        if new != tag.name:
            old = tag.name
            for model in (KBDocument, KBChunk):
                await db.execute(
                    update(model).where(model.tags.contains([old])).values(tags=func.array_replace(model.tags, old, new))
                )
            await db.execute(update(KBDocument).where(KBDocument.tags.contains([new])).values(updated_at=now()))
            tag.name = new
    if body.description is not None:
        tag.description = body.description.strip()
    if body.color is not None:
        tag.color = body.color
    await db.commit()
    return tag_out(tag, await usage(db))


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: str, db: DB, _: Editor):
    """Entries that carried only this tag become visible to everyone."""
    tag = await get_tag(db, tag_id)
    for model in (KBDocument, KBChunk):
        await db.execute(
            update(model).where(model.tags.contains([tag.name])).values(tags=func.array_remove(model.tags, tag.name))
        )
    await db.delete(tag)
    await db.commit()
