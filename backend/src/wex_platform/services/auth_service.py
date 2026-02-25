"""Authentication service: password hashing and JWT token management."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.domain.models import Company, User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    name: str,
    role: str,
    company: str | None = None,
    phone: str | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=role,
        company=company,
        phone=phone,
    )
    db.add(user)
    await db.flush()

    # Auto-create a Company record for the new user
    company_record = Company(name=user.name, type="individual")
    db.add(company_record)
    await db.flush()

    user.company_id = company_record.id
    user.company_role = "admin"

    await db.commit()
    await db.refresh(user)
    return user
