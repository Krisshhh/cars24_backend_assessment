from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import engine
from app.errors import register_exception_handlers
from app.middleware import RequestContextMiddleware, configure_logging
from app.models import Base
from app.routers import health, orders, query

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AI Operations Copilot",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(orders.router)
app.include_router(query.router)
