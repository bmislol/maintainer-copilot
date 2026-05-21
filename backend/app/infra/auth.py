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

from fastapi import Depends, Request
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
