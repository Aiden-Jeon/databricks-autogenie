"""OAuth2 authentication middleware for Databricks Apps.

Unified authentication for both Lamp and Enhancer workflows.
Supports:
1. User Token (X-Forwarded-Access-Token) - for user-scoped operations
2. Service Principal (OAuth/PAT) - for app-level operations
3. Databricks CLI - for local development
"""

import os
import logging
import json
import subprocess
import base64
import time
from typing import Dict, Optional

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


# ========== User Authentication ==========

def get_databricks_cli_token() -> Optional[str]:
    """Get authentication token from Databricks CLI for local development.

    Returns:
        OAuth token from Databricks CLI, or None if unavailable
    """
    try:
        databricks_host = os.getenv("DATABRICKS_HOST")
        if not databricks_host:
            logger.warning("DATABRICKS_HOST not set, cannot get CLI token")
            return None

        result = subprocess.run(
            ["databricks", "auth", "token", "--host", databricks_host],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            token_data = json.loads(result.stdout)
            access_token = token_data.get("access_token")
            logger.info("Successfully obtained token from Databricks CLI")
            return access_token
        else:
            logger.warning(f"Failed to get CLI token: {result.stderr}")
            return None

    except Exception as e:
        logger.warning(f"Error getting CLI token: {e}")
        return None


async def get_current_user(request: Request) -> Dict:
    """Extract user OAuth token from Databricks Apps request headers.

    In Databricks Apps (production), the user's OAuth token is automatically
    injected in the x-forwarded-access-token header by the Databricks gateway.

    In local development, tries to get a token from the Databricks CLI.

    Args:
        request: FastAPI request object

    Returns:
        Dict with user_id and token

    Raises:
        HTTPException: If token is missing and cannot be obtained from CLI
    """
    user_token = request.headers.get('x-forwarded-access-token')

    if not user_token:
        logger.info("No token in headers, attempting to get from Databricks CLI")
        user_token = get_databricks_cli_token()

        if not user_token:
            logger.error("No authentication token available")
            raise HTTPException(
                status_code=401,
                detail="No user authentication token found. For local development, ensure Databricks CLI is configured."
            )

    user_id = extract_user_id_from_token(user_token)
    logger.info(f"Authenticated user: {user_id}")

    return {
        "user_id": user_id,
        "token": user_token
    }


def get_user_token(request: Request) -> str:
    """Extract user's access token from request headers.

    Args:
        request: FastAPI Request object

    Returns:
        User's access token

    Raises:
        HTTPException: If token is missing
    """
    token = request.headers.get("X-Forwarded-Access-Token")
    if not token:
        # Try to get from Databricks CLI for local development
        token = get_databricks_cli_token()
        if not token:
            raise HTTPException(
                status_code=401,
                detail="User authentication required. X-Forwarded-Access-Token header missing."
            )
    return token


def get_user_email(request: Request) -> Optional[str]:
    """Extract user's email from request headers."""
    return request.headers.get("X-Forwarded-Email")


def extract_user_id_from_token(token: str) -> str:
    """Decode JWT token to extract user email/id.

    The token is already validated by the Databricks gateway,
    so we only need to decode it to extract user identity.

    Args:
        token: OAuth2 JWT token

    Returns:
        User email or ID
    """
    try:
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("email") or payload.get("sub") or "unknown_user"
        logger.debug(f"Extracted user_id from token: {user_id}")
        return user_id
    except Exception as e:
        logger.warning(f"Failed to decode JWT token: {e}, using fallback user_id")
        return "databricks_user"


# ========== OBO Token Validation ==========

def _decode_token_claims(token: str) -> Optional[Dict]:
    """Try to decode JWT claims from a token.

    Returns decoded claims dict, or None if the token is opaque / not a JWT.
    """
    try:
        import jwt
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None


def validate_obo_token(token: str, from_gateway: bool) -> Dict:
    """Validate that a token is suitable for user-scoped (OBO) operations.

    Validation strategy:
    - If the token arrived via X-Forwarded-Access-Token, the Databricks
      gateway already guarantees it is a user OBO token. We only do
      best-effort expiration checking.
    - If the token came from the CLI fallback (local dev), we similarly
      trust the Databricks CLI but still check expiration.
    - If the token is a decodable JWT, we additionally reject tokens that
      are positively identifiable as service-principal tokens (have an
      'azp' matching DATABRICKS_CLIENT_ID with no user identity claims).

    Args:
        token: OAuth2 bearer token (JWT or opaque)
        from_gateway: True if the token was received from the
                      X-Forwarded-Access-Token header

    Returns:
        Dict with decoded claims (or empty dict for opaque tokens)

    Raises:
        HTTPException: If token is expired or identified as a service principal token
    """
    claims = _decode_token_claims(token)

    # Opaque (non-JWT) tokens: if from gateway/CLI, trust them.
    if claims is None:
        if from_gateway:
            logger.info("OBO validation: opaque token from gateway, accepted")
            return {}
        # Even CLI tokens can be opaque; trust the source
        logger.info("OBO validation: opaque token from CLI fallback, accepted")
        return {}

    # JWT token — check expiration
    exp = claims.get("exp")
    if exp and time.time() > exp:
        raise HTTPException(
            status_code=401,
            detail="Token has expired. Please refresh your session."
        )

    # Detect service-principal tokens: they typically carry no user
    # identity claims (no email / unique_name / preferred_username)
    # and their 'azp' matches the app's own client ID.
    has_user_identity = bool(
        claims.get("email")
        or claims.get("unique_name")
        or claims.get("preferred_username")
    )

    if not has_user_identity:
        app_client_id = os.getenv("DATABRICKS_CLIENT_ID", "")
        azp = claims.get("azp", "")

        if app_client_id and azp == app_client_id:
            sub = claims.get("sub", "unknown")
            logger.warning(
                f"Token rejected: azp matches app client_id and no user identity "
                f"claims found (sub={sub}). This is a service principal token."
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "User authentication required. Service principal tokens "
                    "cannot be used for this operation. Genie space operations "
                    "require on-behalf-of (OBO) user authentication."
                )
            )

        # No user-identity claims but not positively a SP token either.
        # If it came from the gateway, trust it.
        if from_gateway:
            logger.info(
                "OBO validation: JWT without email claim, but from gateway — accepted"
            )
        else:
            logger.warning(
                "OBO validation: JWT without user identity claims (non-gateway). "
                "Proceeding, but this may indicate a misconfigured token."
            )

    return claims


async def get_obo_user(request: Request) -> Dict:
    """Extract and validate that the request carries a user OBO token.

    Like get_current_user(), but additionally validates that the token
    is suitable for user-scoped operations (not a service principal token,
    not expired).

    Args:
        request: FastAPI request object

    Returns:
        Dict with user_id, token, and token_claims

    Raises:
        HTTPException: If token is missing, expired, or identified as a
                       service principal token
    """
    # Track whether the token came from the gateway header
    from_gateway = bool(request.headers.get('x-forwarded-access-token'))

    user_info = await get_current_user(request)
    token = user_info["token"]

    claims = validate_obo_token(token, from_gateway=from_gateway)
    user_info["token_claims"] = claims
    user_info["from_gateway"] = from_gateway

    return user_info


# ========== Service Principal Authentication ==========

def get_workspace_host() -> str:
    """Get the Databricks workspace host URL.

    Returns:
        Workspace host URL with https:// prefix

    Raises:
        HTTPException: If host is not configured
    """
    host = os.getenv("DATABRICKS_HOST") or os.getenv("DATABRICKS_SERVER_HOSTNAME")

    if not host:
        raise HTTPException(
            status_code=500,
            detail="Databricks workspace host not configured"
        )

    # Clean up template placeholders if present
    if host.startswith("{{"):
        host = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
        if not host or host.startswith("{{"):
            raise HTTPException(
                status_code=500,
                detail="Databricks workspace host not properly configured"
            )

    if not host.startswith("http"):
        host = f"https://{host}"

    return host


def get_service_token() -> str:
    """Get the service PAT token for backend operations.

    Tries multiple sources:
    1. DATABRICKS_SERVICE_TOKEN environment variable
    2. Fetch from secrets scope using app credentials

    Returns:
        Service PAT token

    Raises:
        HTTPException: If token is not configured
    """
    token = os.getenv("DATABRICKS_SERVICE_TOKEN")

    if token and not token.startswith("{{"):
        return token

    # Fallback: Fetch from secrets using app credentials
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.config import Config

        logger.info("Attempting to fetch service token from secrets...")

        client_id = os.getenv("DATABRICKS_CLIENT_ID")
        client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")
        host = get_workspace_host()

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail="App credentials not available to fetch service token"
            )

        config = Config(
            host=host,
            client_id=client_id,
            client_secret=client_secret
        )
        client = WorkspaceClient(config=config)

        # Try to fetch from autogenie scope first, then fall back to genie-enhancement
        for scope in ["autogenie", "genie-enhancement", "genie-lamp"]:
            try:
                secret_value = client.secrets.get_secret(scope=scope, key="service-token")
                if secret_value and secret_value.value:
                    token = secret_value.value
                    # Databricks SDK may return base64-encoded values
                    try:
                        decoded = base64.b64decode(token).decode('utf-8')
                        token = decoded
                    except Exception:
                        pass
                    logger.info(f"Successfully fetched service token from {scope} scope")
                    return token
            except Exception:
                continue

        raise HTTPException(
            status_code=500,
            detail="Service token not found in any secrets scope"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch service token: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch service token: {str(e)}"
        )


def create_user_workspace_client(request: Request):
    """Create WorkspaceClient authenticated as the end user.

    Uses X-Forwarded-Access-Token header for user-scoped operations.

    Args:
        request: FastAPI Request object

    Returns:
        WorkspaceClient authenticated as user

    Raises:
        HTTPException: If user token is missing
    """
    from databricks.sdk import WorkspaceClient

    user_token = get_user_token(request)
    host = get_workspace_host()

    # Clear OAuth env vars to prevent conflict with PAT auth
    saved_client_id = os.environ.pop('DATABRICKS_CLIENT_ID', None)
    saved_client_secret = os.environ.pop('DATABRICKS_CLIENT_SECRET', None)

    try:
        client = WorkspaceClient(host=host, token=user_token)
        return client
    finally:
        if saved_client_id:
            os.environ['DATABRICKS_CLIENT_ID'] = saved_client_id
        if saved_client_secret:
            os.environ['DATABRICKS_CLIENT_SECRET'] = saved_client_secret


def create_service_principal_client():
    """Create WorkspaceClient authenticated as the app's service principal.

    Uses OAuth credentials (DATABRICKS_CLIENT_ID/CLIENT_SECRET) automatically
    provided by Databricks Apps runtime.

    Returns:
        WorkspaceClient authenticated as service principal

    Raises:
        HTTPException: If OAuth credentials are missing
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config

    client_id = os.getenv("DATABRICKS_CLIENT_ID")
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")
    host = get_workspace_host()

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Service principal OAuth credentials not configured."
        )

    config = Config(
        host=host,
        client_id=client_id,
        client_secret=client_secret
    )

    return WorkspaceClient(config=config)


def get_app_oauth_token() -> str:
    """Get OAuth M2M token for app's service principal.

    Uses DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET env vars
    automatically provided by Databricks Apps.

    Returns:
        Bearer token for app authentication

    Raises:
        HTTPException: If unable to obtain OAuth token
    """
    from databricks.sdk.core import Config

    client_id = os.getenv("DATABRICKS_CLIENT_ID")
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="App OAuth credentials not configured (DATABRICKS_CLIENT_ID/CLIENT_SECRET)"
        )

    try:
        cfg = Config()  # Auto-picks up CLIENT_ID, CLIENT_SECRET, HOST
        auth_headers = cfg.authenticate()

        auth_header = auth_headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=500,
                detail="Failed to obtain OAuth token from Databricks SDK"
            )

        return auth_header[7:]  # Remove "Bearer " prefix
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get app OAuth token: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to obtain app OAuth token: {str(e)}"
        )
