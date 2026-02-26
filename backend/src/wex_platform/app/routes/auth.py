"""Authentication routes: signup, login, me, profile update."""

import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.enums import (
    EngagementActor,
    EngagementEventType,
    EngagementStatus,
)
from wex_platform.domain.models import Engagement, EngagementEvent, User
from wex_platform.domain.schemas import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from wex_platform.infra.database import get_db
from wex_platform.services.auth_service import (
    create_access_token,
    create_user,
    decode_token,
    get_user_by_email,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def get_current_user_dep(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency: extract current user from Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )
    token = auth_header.removeprefix("Bearer ")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_role(*roles: str):
    """Factory: dependency that checks user has one of the required roles."""

    async def checker(user: User = Depends(get_current_user_dep)):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


@router.post("/signup", response_model=TokenResponse)
async def signup(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await create_user(
        db, data.email, data.password, data.name, data.role, data.company, data.phone
    )

    # If engagement_id provided and engagement is in buyer_accepted state, link it
    linked_engagement_id = None
    if data.engagement_id:
        result = await db.execute(
            select(Engagement).where(
                Engagement.id == str(data.engagement_id),
                Engagement.status == EngagementStatus.BUYER_ACCEPTED.value,
            )
        )
        engagement = result.scalar_one_or_none()
        if engagement:
            now = datetime.now(timezone.utc)
            engagement.buyer_id = user.id
            engagement.account_created_at = now
            engagement.status = EngagementStatus.ACCOUNT_CREATED.value
            engagement.updated_at = now

            event = EngagementEvent(
                id=str(uuid.uuid4()),
                engagement_id=engagement.id,
                event_type=EngagementEventType.ACCOUNT_CREATED.value,
                actor=EngagementActor.BUYER.value,
                actor_id=user.id,
                from_status=EngagementStatus.BUYER_ACCEPTED.value,
                to_status=EngagementStatus.ACCOUNT_CREATED.value,
                data={"method": "registration", "user_id": user.id},
            )
            db.add(event)
            linked_engagement_id = str(data.engagement_id)
            logger.info(
                "Signup linked engagement %s to user %s", engagement.id, user.id
            )

    await db.commit()
    token = create_access_token(user.id, user.role)
    response = TokenResponse(access_token=token, user=UserResponse.model_validate(user))
    resp_dict = response.model_dump()
    if linked_engagement_id:
        resp_dict["engagement_id"] = linked_engagement_id
    return resp_dict


# /register alias for spec compliance
@router.post("/register", response_model=TokenResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    return await signup(data=data, db=db)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user_dep)):
    return UserResponse.model_validate(user)


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    data: UserUpdate,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    if data.name is not None:
        user.name = data.name
    if data.company is not None:
        user.company = data.company
    if data.phone is not None:
        user.phone = data.phone
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)
