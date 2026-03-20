"""Helper for obtaining OAuth M2M tokens for app authentication."""

import os
import time
import logging
from typing import Optional
from databricks.sdk.core import Config

logger = logging.getLogger(__name__)

_app_token_cache: Optional[dict] = None


def get_app_oauth_token(force_refresh: bool = False) -> str:
    """
    Get OAuth M2M token for app's service principal.

    Uses DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET env vars
    automatically provided by Databricks Apps.

    Args:
        force_refresh: Force token refresh even if cached token is valid

    Returns:
        Bearer token for app authentication (cached with 1-hour expiry)

    Raises:
        ValueError: If unable to obtain OAuth token
    """
    global _app_token_cache

    # Check cache
    if not force_refresh and _app_token_cache:
        expires_at = _app_token_cache.get('expires_at', 0)
        if time.time() < expires_at - 300:  # 5 min buffer
            logger.debug("Using cached app OAuth token")
            return _app_token_cache['token']

    logger.info("Obtaining fresh app OAuth token from Databricks SDK")

    # Get fresh token using Databricks SDK
    cfg = Config()  # Auto-picks up CLIENT_ID, CLIENT_SECRET, HOST
    auth_headers = cfg.authenticate()

    auth_header = auth_headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise ValueError("Failed to obtain OAuth token from Databricks SDK")

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Cache token (expires in 1 hour)
    _app_token_cache = {
        'token': token,
        'expires_at': time.time() + 3600
    }

    logger.info(f"Successfully obtained app OAuth token (expires in 1 hour)")
    logger.debug(f"Token prefix: {token[:10]}...")

    return token
