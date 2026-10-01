from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.api.schemas import TokenOut, UserOut
from app.core import ratelimit
from app.core.security import create_token, verify_password
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(request: Request, db: DB, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    email = form.username.strip().lower()
    keys = (f"ip:{request.client.host if request.client else '?'}", f"email:{email}")
    if wait := ratelimit.locked_for(*keys):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Çok fazla hatalı giriş denemesi. {wait // 60 + 1} dakika sonra tekrar deneyin.",
            headers={"Retry-After": str(wait)},
        )
    user = await db.scalar(select(User).where(User.email == email))
    # verify_password runs even for unknown e-mails, so timing reveals nothing.
    ok = verify_password(form.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        ratelimit.record_failure(*keys)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya şifre hatalı.")
    ratelimit.clear(*keys)
    return TokenOut(access_token=create_token(user.id, user.token_version), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
