"""DialogAI API.  Run: uvicorn app.main:app --port 8000  (from backend/)"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import func, select

from app.api import agents, auth, demo, knowledge, meta, scenarios, sessions, tags, users
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import SessionLocal, run_migrations
from app.db.models import User
from app.kb import ingest
from app.simulation import service as simulation
from app.runtime.providers import STTSettings
from app.runtime.voice import build_stt, setup_cuda_dlls


async def bootstrap_admin() -> None:
    async with SessionLocal() as db:
        if await db.scalar(select(func.count()).select_from(User)):
            return
        db.add(
            User(
                email=settings.bootstrap_admin_email,
                name="Yönetici",
                role="admin",
                password_hash=hash_password(settings.bootstrap_admin_password),
            )
        )
        await db.commit()
        logger.warning(
            f"Created initial admin {settings.bootstrap_admin_email}; change its password."
        )


async def warm_up_whisper() -> None:
    """Load the default Whisper model in the background so the first voice call starts fast."""
    try:
        await asyncio.to_thread(build_stt, STTSettings())
        logger.info("Whisper model loaded")
    except Exception as e:  # voice calls will report it; text calls don't need Whisper
        logger.warning(f"Whisper warm-up failed: {e}")


def check_settings() -> None:
    problems = settings.production_problems()
    if settings.production and problems:
        raise RuntimeError("Üretim ayarları güvenli değil:\n- " + "\n- ".join(problems))
    for problem in problems:
        logger.warning(f"Geliştirme ayarı (üretimde başlatılmaz): {problem}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_settings()
    setup_cuda_dlls()
    if settings.run_migrations:
        await asyncio.to_thread(run_migrations)
    await bootstrap_admin()
    await ingest.start_worker()
    await simulation.start_worker()
    warmup = asyncio.create_task(warm_up_whisper()) if settings.warmup_whisper else None
    yield
    if warmup:
        warmup.cancel()
    await ingest.stop_worker()
    await simulation.stop_worker()


# The interactive API docs describe every endpoint; production doesn't publish them.
docs = {} if not settings.production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="DialogAI", lifespan=lifespan, **docs)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"  # API answers carry user data
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (auth, users, agents, knowledge, tags, scenarios, sessions, meta):
    app.include_router(module.router)
if settings.demo_api_enabled:
    app.include_router(demo.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
