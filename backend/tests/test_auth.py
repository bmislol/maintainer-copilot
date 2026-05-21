"""Auth tests — Phase 4.1.

All five tests use dependency overrides so no live database or Vault
connection is needed. The override replaces:
  - get_user_manager  → injects a mock UserManager with two pre-built users
  - get_jwt_strategy  → returns a JWTStrategy with a fixed test secret

FastAPI dependency overrides work by function identity, so we import the
original functions and add them to app.dependency_overrides. The fixture
cleans up overrides after each test to avoid bleed-through.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.db.models.users import User
from app.infra.auth import current_active_superuser

# ---------------------------------------------------------------------------
# Constants for test users
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-jwt-secret-for-unit-tests-only"
_USER_ID = uuid.uuid4()
_ADMIN_ID = uuid.uuid4()
_USER_EMAIL = "user@example.com"
_ADMIN_EMAIL = "admin@example.com"
_USER_PASSWORD = "userpass123"
_ADMIN_PASSWORD = "adminpass123"


def _make_user(
    *,
    user_id: uuid.UUID,
    email: str,
    password: str,
    is_superuser: bool,
) -> User:
    """Build a User instance with a real bcrypt hash for the given password."""
    from fastapi_users.password import PasswordHelper

    user = User()
    user.id = user_id
    user.email = email
    user.hashed_password = PasswordHelper().hash(password)
    user.is_active = True
    user.is_verified = True
    user.is_superuser = is_superuser
    return user


# ---------------------------------------------------------------------------
# Fixture: app with dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_app() -> FastAPI:
    """Return the main FastAPI app with auth deps overridden for unit testing."""
    from fastapi_users.authentication import JWTStrategy
    from fastapi_users.db import SQLAlchemyUserDatabase

    from app.infra.auth import get_jwt_strategy, get_user_manager
    from app.main import app

    regular = _make_user(
        user_id=_USER_ID, email=_USER_EMAIL, password=_USER_PASSWORD, is_superuser=False
    )
    admin = _make_user(
        user_id=_ADMIN_ID, email=_ADMIN_EMAIL, password=_ADMIN_PASSWORD, is_superuser=True
    )

    users_by_email = {regular.email: regular, admin.email: admin}
    users_by_id: dict[uuid.UUID, User] = {regular.id: regular, admin.id: admin}

    mock_db: MagicMock = MagicMock(spec=SQLAlchemyUserDatabase)
    mock_db.get_by_email = AsyncMock(side_effect=lambda email: users_by_email.get(email))
    mock_db.get = AsyncMock(side_effect=lambda uid: users_by_id.get(uid))

    async def _override_get_user_manager() -> AsyncGenerator[object, None]:
        from app.infra.auth import UserManager

        yield UserManager(mock_db)

    def _override_get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
        return JWTStrategy(secret=_TEST_SECRET, lifetime_seconds=3600, algorithm="HS256")

    app.dependency_overrides[get_user_manager] = _override_get_user_manager
    app.dependency_overrides[get_jwt_strategy] = _override_get_jwt_strategy
    yield app  # type: ignore[misc]
    app.dependency_overrides.clear()


async def _get_token(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_correct_credentials_returns_token(auth_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        resp = await client.post(
            "/auth/jwt/login",
            data={"username": _USER_EMAIL, "password": _USER_PASSWORD},
        )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password_returns_400(auth_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        resp = await client.post(
            "/auth/jwt/login",
            data={"username": _USER_EMAIL, "password": "wrong-password"},
        )
    # fastapi-users returns 400 LOGIN_BAD_CREDENTIALS, not 401.
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_users_me_with_valid_token(auth_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        token = await _get_token(client, _USER_EMAIL, _USER_PASSWORD)
        resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == _USER_EMAIL


@pytest.mark.asyncio
async def test_users_me_without_token_returns_401(auth_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        resp = await client.get("/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_blocked_from_admin_route(auth_app: FastAPI) -> None:
    """Regular (non-superuser) user is blocked from a route requiring is_superuser."""
    from fastapi import Depends
    from fastapi.responses import JSONResponse

    @auth_app.get("/admin/only-for-test")
    async def admin_only(
        _user: User = Depends(current_active_superuser),
    ) -> JSONResponse:
        return JSONResponse({"ok": True})

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        token = await _get_token(client, _USER_EMAIL, _USER_PASSWORD)
        resp = await client.get(
            "/admin/only-for-test", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 403
