"""
Secret Manager — resolves secret names to actual values.

Priority:
1. Environment variables (AGENTBOX_SECRET_{TENANT}_{NAME})
2. .env file
3. secrets/ directory (one file per secret)

Example:
    resolve_secret("j-one-studio", "umnico_token")
    -> looks for env AGENTBOX_SECRET_J_ONE_STUDIO_UMNICO_TOKEN
    -> falls back to secrets/j-one-studio/umnico_token
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_secret(tenant_slug: str, secret_name: str) -> str | None:
    """
    Resolve a secret by name for a specific tenant.

    Args:
        tenant_slug: Tenant identifier (e.g., "j-one-studio")
        secret_name: Secret name (e.g., "umnico_token", "openai_key")

    Returns:
        Secret value or None if not found.
    """
    # 1. Try environment variable.
    env_key = f"AGENTBOX_SECRET_{_slugify(tenant_slug)}_{_slugify(secret_name)}"
    value = os.environ.get(env_key)
    if value:
        return value

    # 2. Try secrets directory.
    secrets_dir = Path("secrets") / tenant_slug
    secret_file = secrets_dir / secret_name
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()

    logger.warning("Secret not found: %s/%s", tenant_slug, secret_name)
    return None


def _slugify(s: str) -> str:
    """Convert slug to env-safe format: j-one-studio -> J_ONE_STUDIO."""
    return s.replace("-", "_").upper()

