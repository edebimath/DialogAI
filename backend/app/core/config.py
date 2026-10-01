import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]  # repo root (DialogAI/)

# Development defaults; production refuses to start with them.
DEV_JWT_SECRET = "dev-secret-change-me"
DEV_ADMIN_PASSWORD = "admin123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # production: refuses to start with default secrets, hides the API docs, turns the demo
    # APIs off unless DEMO_API=true. See check_production().
    app_env: Literal["development", "production"] = "development"

    data_dir: Path = ROOT / "data"
    # PostgreSQL with the pgvector extension, e.g.
    # postgresql+asyncpg://dialogai:<password>@127.0.0.1:5432/dialogai
    database_url: str = "postgresql+asyncpg://dialogai:dialogai@127.0.0.1:5432/dialogai"

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 60 * 12

    # First run creates this admin if the users table is empty.
    bootstrap_admin_email: str = "admin@dialogai.local"
    bootstrap_admin_password: str = DEV_ADMIN_PASSWORD

    cors_origins: list[str] = ["http://localhost:5173"]

    # Stand-in business APIs for the templates (/api/demo); None = on in development only.
    demo_api: bool | None = None

    # HTTP Aracı: hosts it may call ("crm.sirket.local", "*.sirket.local"). Empty = any host
    # except blocked ones (cloud metadata, link-local, this system's database and Ollama).
    http_tool_allowed_hosts: list[str] = []
    http_tool_max_response_bytes: int = 1024 * 1024

    # Failed logins per IP and per e-mail before a temporary lock.
    login_max_failures: int = 5
    login_lock_minutes: int = 5

    # 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and every new
    # connection loses ~2 s before falling back.
    ollama_url: str = "http://127.0.0.1:11434"
    google_api_key: str = ""

    # Knowledge base
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embed_on_gpu: bool = False  # CPU keeps VRAM for the LLM and Whisper; ~30 ms per query
    kb_min_score: float = 0.45  # cosine similarity below this is "not found"

    # Simulated callers and the judge (Ollama model name)
    simulation_model: str = "qwen3:8b"

    # Whisper: "cuda" needs an NVIDIA GPU (Docker: the gpu override); "cpu" is slower but runs anywhere.
    whisper_device: Literal["cuda", "cpu"] = "cuda"
    whisper_compute_type: str = ""  # empty: int8_float16 on cuda, int8 on cpu

    max_concurrent_sessions: int = 4
    warmup_whisper: bool = True  # load the STT model at startup (off in tests)
    run_migrations: bool = True  # alembic upgrade head at startup (tests create tables directly)
    db_pool: bool = True  # tests turn pooling off: asyncpg connections are bound to one event loop

    @property
    def ollama_openai_url(self) -> str:
        return f"{self.ollama_url}/v1"

    @property
    def production(self) -> bool:
        return self.app_env == "production"

    @property
    def demo_api_enabled(self) -> bool:
        return (not self.production) if self.demo_api is None else self.demo_api

    def secret(self, name: str) -> str | None:
        """A secret for HTTP Aracı, {{ secret.crm_token }} -> environment SECRET_CRM_TOKEN.
        Kept out of flows so API keys never sit in the database or reach viewers."""
        return os.environ.get(f"SECRET_{name.upper()}") or _dotenv_secrets().get(f"SECRET_{name.upper()}")

    def production_problems(self) -> list[str]:
        """Settings that must not reach production; the API refuses to start with any."""
        problems = []
        if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET en az 32 karakterlik rastgele bir değer olmalı.")
        if self.bootstrap_admin_password == DEV_ADMIN_PASSWORD or len(self.bootstrap_admin_password) < 12:
            problems.append("BOOTSTRAP_ADMIN_PASSWORD varsayılan olmamalı ve en az 12 karakter olmalı.")
        if "dialogai:dialogai@" in self.database_url:
            problems.append("DATABASE_URL varsayılan veritabanı şifresini kullanıyor.")
        return problems



def _dotenv_secrets() -> dict[str, str]:
    """SECRET_* entries of .env (pydantic-settings ignores keys it has no field for)."""
    env = ROOT / ".env"
    if not env.exists():
        return {}
    pairs = (line.split("=", 1) for line in env.read_text("utf-8-sig").splitlines() if "=" in line)
    return {k.strip(): v.strip() for k, v in pairs if k.strip().startswith("SECRET_")}


settings = Settings()
