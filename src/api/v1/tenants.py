from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config_loader import list_tenants as list_tenant_dirs
from src.db import get_db
from src.models import Tenant

from .schemas import TenantResponse


router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.get("/discover", response_model=list[str])
async def discover_tenants() -> list[str]:
    """
    Discover tenant slugs from the filesystem (tenants/* directories).

    This is useful on a clean DB so the web panel can suggest available configs
    before tenants are registered in PostgreSQL.
    """
    return list_tenant_dirs("tenants")


@router.get("", response_model=list[TenantResponse])
async def list_tenants(db: AsyncSession = Depends(get_db)) -> list[TenantResponse]:
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()
    return [TenantResponse.model_validate(t) for t in tenants]
