"""Auth routers — login, logout, /users/me.

Deliberately does NOT mount the register router. Registration is
admin-invite-only; new users are created via bootstrap_admin.py or a
future admin API endpoint (Phase 4.1 scope excludes user invitation UI).

Layer: app/api/
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.schemas import UserRead, UserUpdate
from app.infra.auth import auth_backend, fastapi_users

router = APIRouter()

# Login (POST /auth/jwt/login) and logout (POST /auth/jwt/logout).
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# /users/me — GET and PATCH for the authenticated user.
# No /users/{id} admin routes exposed here; kept out of scope for Phase 4.1.
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
