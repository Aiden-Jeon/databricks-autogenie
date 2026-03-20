"""Shared middleware for AutoGenie."""

from backend.middleware.auth import (
    get_current_user,
    get_user_token,
    get_service_token,
    get_workspace_host,
    create_user_workspace_client,
    create_service_principal_client,
)

__all__ = [
    "get_current_user",
    "get_user_token",
    "get_service_token",
    "get_workspace_host",
    "create_user_workspace_client",
    "create_service_principal_client",
]
