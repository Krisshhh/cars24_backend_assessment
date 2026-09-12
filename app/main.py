from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import engine
from app.models import Base

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AI Operations Copilot",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
