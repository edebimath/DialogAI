from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.flows.templates import TEMPLATES
from app.runtime.providers import PROVIDERS

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/templates")
async def templates(_: CurrentUser):
    return [
        {"key": key, "name": t["name"], "description": t["description"]}
        for key, t in TEMPLATES.items()
    ]


@router.get("/providers")
async def providers(_: CurrentUser):
    return PROVIDERS
