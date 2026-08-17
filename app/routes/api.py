"""Endpoint HTTP. Semuanya ringan -- kerja berat ada di worker."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from rq import Queue

from app import jobs, tasks
from app.config import settings
from app.formats import DEFAULT_PRESET, get_preset, list_presets
from app.ratelimit import RateLimitExceeded, client_identifier, enforce_rate_limit
from app.validators import UrlValidationError, validate_url

router = APIRouter(prefix="/api")

queue = Queue(
    "downloads",
    connection=jobs.get_rq_redis(),
    default_timeout=settings.job_timeout_seconds,
)


class JobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    preset: str = Field(default=DEFAULT_PRESET, max_length=32)


class ProbeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


def _validated_url(raw: str) -> str:
    try:
        return validate_url(raw, settings.allowed_domain_list)
    except UrlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _guard(request: Request, scope: str) -> None:
    try:
        enforce_rate_limit(client_identifier(request), scope=scope)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak permintaan. Coba lagi nanti.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


@router.get("/presets")
def presets() -> dict:
    return {"presets": list_presets(), "default": DEFAULT_PRESET}


@router.post("/probe")
async def probe(payload: ProbeRequest, request: Request) -> dict:
    """Ambil metadata saja, tanpa mengunduh.

    Dijalankan di threadpool karena yt-dlp memblokir. Ini satu-satunya
    pemanggilan yt-dlp yang sinkron, dan hanya karena biasanya 1-3 detik.
    """
    _guard(request, scope="probe")
    url = _validated_url(payload.url)

    def _extract() -> dict:
        import yt_dlp

        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
        if settings.proxy:
            opts["proxy"] = settings.proxy
        if settings.cookies_file:
            opts["cookiefile"] = str(settings.cookies_file)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}

    try:
        info = await run_in_threadpool(_extract)
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] gagal: {exc!r}", flush=True)
        raise HTTPException(status_code=502, detail="Tidak bisa membaca informasi video.") from exc

    return {
        "title": info.get("title") or "",
        "uploader": info.get("uploader") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail") or "",
    }


@router.post("/jobs", status_code=202)
def create_job(payload: JobRequest, request: Request) -> dict:
    _guard(request, scope="jobs")

    if get_preset(payload.preset) is None:
        raise HTTPException(status_code=400, detail="Preset kualitas tidak dikenal.")
    url = _validated_url(payload.url)

    record = jobs.create_job(url, payload.preset)
    queue.enqueue(
        tasks.run_download,
        record["id"],
        url,
        payload.preset,
        job_timeout=settings.job_timeout_seconds,
    )
    return jobs.to_public(record)


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    record = jobs.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan atau sudah kedaluwarsa.")
    return jobs.to_public(record)


@router.get("/jobs/{job_id}/file")
def job_file(job_id: str) -> FileResponse:
    record = jobs.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan atau sudah kedaluwarsa.")
    if record.get("status") != jobs.STATUS_DONE:
        raise HTTPException(status_code=409, detail="File belum siap.")

    base = (settings.download_dir / job_id).resolve()
    path = (base / record.get("filename", "")).resolve()
    # Pastikan hasil resolve masih di dalam folder job: pertahanan terakhir
    # terhadap path traversal lewat nama file.
    if not path.is_file() or base not in path.parents:
        raise HTTPException(status_code=410, detail="File sudah dihapus dari server.")

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
    )
