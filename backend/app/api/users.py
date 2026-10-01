from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DB, Admin
from app.api.schemas import UserCreate, UserOut, UserUpdate
from app.core.security import hash_password
from app.db.models import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(db: DB, _: Admin):
    return (await db.scalars(select(User).order_by(User.created_at))).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: DB, _: Admin):
    email = body.email.strip().lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu e-posta ile bir kullanıcı zaten var.")
    user = User(email=email, name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UserUpdate, db: DB, admin: Admin):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı.")
    demoting = (body.role not in (None, "admin")) or body.is_active is False
    if user.role == "admin" and demoting:
        admins = await db.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
        )
        if admins <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Son yönetici kaldırılamaz.")
    if body.name is not None:
        user.name = body.name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)
        user.token_version += 1  # signs the user out everywhere
    await db.commit()
    return user
