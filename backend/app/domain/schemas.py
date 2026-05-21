"""Pydantic schemas for API request/response shapes.

Distinct from ORM models (app/db/models/) and domain exceptions
(app/domain/exceptions.py).

fastapi-users requires Read and Update schemas for /users/me.
"""

from __future__ import annotations

import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Response schema for /users/me."""


class UserUpdate(schemas.BaseUserUpdate):
    """Request schema for PATCH /users/me.

    Allows updating email, password, is_active, is_verified.
    is_superuser changes are blocked at the UserManager level for
    non-superusers.
    """
