"""fastapi-users infrastructure — UserDatabase, UserManager, JWT backend.

Layer: app/infra/
Used by: app/api/auth.py (mounts routers), app/entrypoints/bootstrap_admin.py.

JWT secret threading
--------------------
The JWT signing key lives in Vault and is resolved during lifespan startup
into ``app.state.secrets.jwt``. ``get_jwt_strategy`` is a FastAPI dependency
that receives the current ``Request`` and reads the key at request time —
never at module import time. ``AuthenticationBackend`` accepts any
``DependencyCallable`` for ``get_strategy``, so this works with no extra
indirection.

Role model
----------
``is_superuser`` is used as the admin flag (D-033). Two roles (user / admin)
map to a boolean; no separate role column is needed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User
from app.db.session import get_async_session

# ---------------------------------------------------------------------------
# Database adapter
# ---------------------------------------------------------------------------


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    """Yield a SQLAlchemyUserDatabase bound to the current request's session."""
    yield SQLAlchemyUserDatabase(session, User)


# ---------------------------------------------------------------------------
# User manager
# ---------------------------------------------------------------------------


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Minimal UserManager — no custom on_after_* hooks needed for this project."""


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


# ---------------------------------------------------------------------------
# JWT authentication backend
# ---------------------------------------------------------------------------

bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")


def get_jwt_strategy(request: Request) -> JWTStrategy[User, uuid.UUID]:
    """Build a JWTStrategy from Vault-resolved secrets stored in app.state.

    Reading at request time means the secret is never captured at import
    time and is always the value loaded by the lifespan.
    """
    jwt = request.app.state.secrets.jwt
    return JWTStrategy(
        secret=jwt.signing_key,
        lifetime_seconds=jwt.access_token_lifetime_seconds,
        algorithm=jwt.algorithm,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# ---------------------------------------------------------------------------
# FastAPIUsers instance + current-user dependencies
# ---------------------------------------------------------------------------

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_active_superuser = fastapi_users.current_user(active=True, superuser=True)

# ---------------------------------------------------------------------------
# Widget auth — widget_id query param (Phase 4.5)
# ---------------------------------------------------------------------------

_WIDGET_SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_widget_user(
    widget_id: str | None = Query(default=None),
) -> User:
    """Validate widget_id and return a system-user stub.

    Phase 4.5: validates UUID format only.
    Phase 4.6: will look up the widget's owning user from the widgets table.
    """
    if not widget_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="widget_id required"
        )
    try:
        uuid.UUID(widget_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid widget_id"
        ) from None
    return User(
        id=_WIDGET_SYSTEM_USER_ID,
        email="widget@system.local",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        hashed_password="",
    )


async def get_current_user_or_widget(
    request: Request,
    widget_id: str | None = Query(default=None),
    user_manager: UserManager = Depends(get_user_manager),
) -> User:
    """Accept either a Bearer JWT or a widget_id query param.

    Tries JWT first (authenticated Streamlit / API sessions).
    Falls back to widget_id (embedded widget sessions).
    Raises 403 if neither is present or valid.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
        strategy = get_jwt_strategy(request)
        try:
            user = await strategy.read_token(token, user_manager)
            if user and user.is_active:
                return user
        except Exception:
            pass  # fall through to widget_id path

    return await get_widget_user(widget_id)
