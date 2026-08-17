"""Penyimpanan status job di Redis.

Job disimpan terpisah dari metadata RQ supaya bentuk data yang dikirim ke
frontend tidak ikut berubah saat versi RQ diganti.
"""

import time
import uuid
from typing import Optional

import redis

from app.config import settings

JOB_PREFIX = "job:"

STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_DONE = "done"
STATUS_ERROR = "error"

# Record job hidup sedikit lebih lama dari filenya, supaya user yang
# polling tetap dapat pesan "file sudah kedaluwarsa" alih-alih 404 kosong.
_JOB_TTL = settings.file_ttl_seconds + 3600

_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
# RQ menyimpan payload biner, jadi butuh koneksi tanpa decode.
_rq_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=False)


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


def get_rq_redis() -> redis.Redis:
    return redis.Redis(connection_pool=_rq_pool)


def _key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


def create_job(url: str, preset_id: str) -> dict:
    job_id = uuid.uuid4().hex
    record = {
        "id": job_id,
        "url": url,
        "preset": preset_id,
        "status": STATUS_QUEUED,
        "progress": "0",
        "created_at": str(int(time.time())),
        "title": "",
        "error": "",
        "filename": "",
        "filesize": "0",
    }
    conn = get_redis()
    conn.hset(_key(job_id), mapping=record)
    conn.expire(_key(job_id), _JOB_TTL)
    return record


def get_job(job_id: str) -> Optional[dict]:
    # job_id selalu hex UUID yang kita buat sendiri; tolak apa pun selain itu
    # supaya tidak ada key Redis lain yang bisa dibaca lewat URL.
    if not job_id or len(job_id) != 32 or not all(c in "0123456789abcdef" for c in job_id):
        return None
    record = get_redis().hgetall(_key(job_id))
    return record or None


def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    mapping = {k: ("" if v is None else str(v)) for k, v in fields.items()}
    conn = get_redis()
    conn.hset(_key(job_id), mapping=mapping)
    conn.expire(_key(job_id), _JOB_TTL)


def to_public(record: dict) -> dict:
    """Bentuk yang aman dikirim ke browser (tanpa path absolut di server)."""
    return {
        "id": record.get("id", ""),
        "status": record.get("status", ""),
        "progress": float(record.get("progress") or 0),
        "title": record.get("title", ""),
        "preset": record.get("preset", ""),
        "error": record.get("error", ""),
        "filename": record.get("filename", ""),
        "filesize": int(record.get("filesize") or 0),
    }
