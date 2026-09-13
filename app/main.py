from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

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
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(orders.router)
app.include_router(query.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")
