from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_hasher = PasswordHash.recommended()
ALGORITHM = "HS256"
# Verified against when the e-mail is unknown, so a failed login takes the same time either way
# and response times don't reveal which addresses have accounts.
_DUMMY_HASH = _hasher.hash("dialogai-timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def create_token(user_id: str, token_version: int) -> str:
    """token_version is the user's counter at login; raising it (password change) revokes the token."""
    now = datetime.now(UTC)
    claims = {"sub": user_id, "tv": token_version, "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> tuple[str, int] | None:
    """(user id, token version) of a valid token, else None."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        return None
    return claims["sub"], int(claims.get("tv", 0))
