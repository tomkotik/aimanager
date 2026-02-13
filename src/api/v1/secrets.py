"""
Secrets API — file-based secrets management for tenants.

IMPORTANT: Secret values are never returned by the API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["secrets"])


class SecretInfo(BaseModel):
    name: str
    is_set: bool
    updated_at: str | None = None


class SecretSetRequest(BaseModel):
    value: str


def _validate_secret_name(name: str) -> str:
    if not name or name.startswith("."):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid secret name")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid secret name")
    return name


def _secrets_dir(tenant_slug: str) -> Path:
    return Path("secrets") / tenant_slug


def _ensure_gitignore(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    gitignore = dir_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")


@router.get("/tenants/{slug}/secrets", response_model=list[SecretInfo])
async def list_secrets(slug: str) -> list[SecretInfo]:
    dir_path = _secrets_dir(slug)
    _ensure_gitignore(dir_path)

    items: list[SecretInfo] = []
    for path in sorted(dir_path.iterdir()):
        if not path.is_file() or path.name == ".gitignore":
            continue
        try:
            stat = path.stat()
            updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            is_set = stat.st_size > 0
            items.append(SecretInfo(name=path.name, is_set=is_set, updated_at=updated))
        except OSError:
            logger.warning("Failed to stat secret file: %s", path)
            items.append(SecretInfo(name=path.name, is_set=True, updated_at=None))
    return items


@router.put("/tenants/{slug}/secrets/{name}", response_model=dict)
async def set_secret(slug: str, name: str, payload: SecretSetRequest) -> dict:
    name = _validate_secret_name(name)
    dir_path = _secrets_dir(slug)
    _ensure_gitignore(dir_path)

    path = dir_path / name
    path.write_text(payload.value, encoding="utf-8")
    return {"ok": True}


@router.delete("/tenants/{slug}/secrets/{name}", response_model=dict)
async def delete_secret(slug: str, name: str) -> dict:
    name = _validate_secret_name(name)
    dir_path = _secrets_dir(slug)
    _ensure_gitignore(dir_path)

    path = dir_path / name
    if path.exists():
        path.unlink()
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    return {"ok": True}

