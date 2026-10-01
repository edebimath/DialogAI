from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.base import get_db
from app.db.models import User

Role = Literal["admin", "editor", "viewer"]
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
DB = Annotated[AsyncSession, Depends(get_db)]


async def user_from_token(db: AsyncSession, token: str) -> User | None:
    """The active user a token belongs to; None for invalid, expired or revoked tokens."""
    claims = decode_token(token)
    if claims is None:
        return None
    user_id, token_version = claims
    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        return None
    return user


async def current_user(db: DB, token: Annotated[str, Depends(oauth2)]) -> User:
    user = await user_from_token(db, token)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Oturum geçersiz, lütfen tekrar giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require(role: Role):
    async def check(user: Annotated[User, Depends(current_user)]) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok.")
        return user

    return check


CurrentUser = Annotated[User, Depends(current_user)]
Editor = Annotated[User, Depends(require("editor"))]
Admin = Annotated[User, Depends(require("admin"))]
