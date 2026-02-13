from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.agents import router as agents_router
from src.api.v1.conversations import router as conversations_router
from src.api.v1.analytics import router as analytics_router
from src.api.v1.health import router as health_router
from src.api.v1.knowledge import router as knowledge_router
from src.api.v1.secrets import router as secrets_router
from src.api.v1.tenants import router as tenants_router
from src.api.v1.webhooks import router as webhooks_router
from src.config import get_settings
from src.db import engine


settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup completed")
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("Application shutdown completed")


app = FastAPI(
    title="AgentBox",
    description="Платформа управления AI-агентами",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

origins = (
    [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    if settings.allowed_origins != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(agents_router)
app.include_router(conversations_router)
app.include_router(analytics_router)
app.include_router(knowledge_router)
app.include_router(secrets_router)
app.include_router(tenants_router)
app.include_router(webhooks_router)
