"""
Knowledge Base API — CRUD operations for tenant markdown files.

Files are stored on disk under: tenants/{tenant_slug}/knowledge/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models import Agent, Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


class KnowledgeFileInfo(BaseModel):
    name: str
    size: int
    updated_at: str


class KnowledgeFileResponse(BaseModel):
    name: str
    content: str


class KnowledgeFileUpdateRequest(BaseModel):
    content: str


class KnowledgeFileCreateRequest(BaseModel):
    name: str
    content: str


def _validate_filename(name: str) -> str:
    if not name or name.startswith("."):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return name


async def _get_tenant_slug(db: AsyncSession, agent_id: UUID) -> str:
    result = await db.execute(
        select(Tenant.slug)
        .select_from(Agent)
        .join(Tenant, Agent.tenant_id == Tenant.id)
        .where(Agent.id == agent_id)
    )
    slug = result.scalar_one_or_none()
    if not slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return slug


def _knowledge_dir(tenant_slug: str) -> Path:
    return Path("tenants") / tenant_slug / "knowledge"


@router.get("/agents/{agent_id}/knowledge", response_model=list[KnowledgeFileInfo])
async def list_knowledge_files(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeFileInfo]:
    tenant_slug = await _get_tenant_slug(db, agent_id)
    kb_dir = _knowledge_dir(tenant_slug)
    kb_dir.mkdir(parents=True, exist_ok=True)

    items: list[KnowledgeFileInfo] = []
    for path in sorted(kb_dir.glob("*.md")):
        try:
            stat = path.stat()
            updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            items.append(KnowledgeFileInfo(name=path.name, size=int(stat.st_size), updated_at=updated))
        except OSError:
            logger.warning("Failed to stat KB file: %s", path)
            continue
    return items


@router.get("/agents/{agent_id}/knowledge/{filename}", response_model=KnowledgeFileResponse)
async def get_knowledge_file(
    agent_id: UUID,
    filename: str,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeFileResponse:
    tenant_slug = await _get_tenant_slug(db, agent_id)
    filename = _validate_filename(filename)

    path = _knowledge_dir(tenant_slug) / filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return KnowledgeFileResponse(name=path.name, content=path.read_text(encoding="utf-8"))


@router.put("/agents/{agent_id}/knowledge/{filename}", response_model=KnowledgeFileResponse)
async def update_knowledge_file(
    agent_id: UUID,
    filename: str,
    payload: KnowledgeFileUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeFileResponse:
    tenant_slug = await _get_tenant_slug(db, agent_id)
    filename = _validate_filename(filename)

    kb_dir = _knowledge_dir(tenant_slug)
    kb_dir.mkdir(parents=True, exist_ok=True)
    path = kb_dir / filename

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    path.write_text(payload.content, encoding="utf-8")
    return KnowledgeFileResponse(name=path.name, content=payload.content)


@router.post("/agents/{agent_id}/knowledge", response_model=KnowledgeFileResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_file(
    agent_id: UUID,
    payload: KnowledgeFileCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeFileResponse:
    tenant_slug = await _get_tenant_slug(db, agent_id)
    filename = _validate_filename(payload.name)

    kb_dir = _knowledge_dir(tenant_slug)
    kb_dir.mkdir(parents=True, exist_ok=True)
    path = kb_dir / filename

    if path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="File already exists")

    path.write_text(payload.content, encoding="utf-8")
    return KnowledgeFileResponse(name=path.name, content=payload.content)


@router.delete("/agents/{agent_id}/knowledge/{filename}")
async def delete_knowledge_file(
    agent_id: UUID,
    filename: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_slug = await _get_tenant_slug(db, agent_id)
    filename = _validate_filename(filename)

    path = _knowledge_dir(tenant_slug) / filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    path.unlink()
    return {"ok": True}

