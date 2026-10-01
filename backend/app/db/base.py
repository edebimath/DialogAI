from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


settings.data_dir.mkdir(parents=True, exist_ok=True)
engine = (
    create_async_engine(settings.database_url, pool_pre_ping=True)
    if settings.db_pool
    else create_async_engine(settings.database_url, poolclass=NullPool)
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def run_migrations() -> None:
    """alembic upgrade head. Blocking and runs its own event loop: call it from a thread."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(ALEMBIC_INI)), "head")


async def reset_tables() -> None:
    """Test setup: rebuild the schema straight from the models, without migrations."""
    from app.db import models  # noqa: F401  (registers the tables)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
