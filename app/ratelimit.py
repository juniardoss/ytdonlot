"""Rate limit sederhana berbasis fixed window di Redis.

Tanpa ini, dalam hitungan hari situs akan dipakai orang lain sebagai API
gratis dan kuota bandwidth habis.
"""

import time

from app.config import settings
from app.jobs import get_redis


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Terlalu banyak permintaan.")


def enforce_rate_limit(identifier: str, scope: str = "jobs") -> None:
    window = settings.rate_limit_window_seconds
    now = int(time.time())
    window_start = now - (now % window)
    key = f"rl:{scope}:{window_start}:{identifier}"

    conn = get_redis()
    pipe = conn.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    count, _ = pipe.execute()

    if int(count) > settings.rate_limit_requests:
        raise RateLimitExceeded(retry_after=window_start + window - now)


def client_identifier(request) -> str:
    """IP klien.

    Di belakang reverse proxy, request.client.host adalah IP proxy-nya.
    Jalankan uvicorn dengan --proxy-headers dan set --forwarded-allow-ips
    ke IP proxy supaya X-Forwarded-For dipercaya -- jangan baca header itu
    langsung di sini, karena klien bisa memalsukannya.
    """
    return request.client.host if request.client else "unknown"
