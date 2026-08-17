"""Entry point FastAPI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.jobs import get_redis
from app.routes.api import router as api_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Video Downloader", docs_url="/api/docs", redoc_url=None)
app.include_router(api_router)


@app.on_event("startup")
def ensure_download_dir() -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)


@app.get("/healthz")
def healthz() -> dict:
    try:
        get_redis().ping()
    except Exception:  # noqa: BLE001
        return {"status": "degraded", "redis": False}
    return {"status": "ok", "redis": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
