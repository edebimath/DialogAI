import asyncio
import os
import re
import tempfile
from pathlib import Path

import pytest

# Point the app at the test database and a scratch data directory before its settings load.
_env = Path(__file__).resolve().parents[2] / ".env"
_test_url = os.environ.get("TEST_DATABASE_URL") or next(
    (m.group(1) for m in re.finditer(r"^﻿?TEST_DATABASE_URL=(.+)$", _env.read_text("utf-8-sig"), re.M)),
    None,
)
if not _test_url:
    raise RuntimeError("TEST_DATABASE_URL is not set (.env); tests need a PostgreSQL test database.")
os.environ["DATABASE_URL"] = _test_url
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="dialogai-test-")
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "admin@test.local"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "secret123"
os.environ["WARMUP_WHISPER"] = "false"
os.environ["RUN_MIGRATIONS"] = "false"
os.environ["DB_POOL"] = "false"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40


@pytest.fixture(scope="session", autouse=True)
def database():
    from app.db.base import reset_tables

    asyncio.run(reset_tables())
