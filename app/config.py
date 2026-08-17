"""Konfigurasi aplikasi, dibaca dari environment / file .env."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Domain yang boleh diproses. Ini adalah pertahanan utama terhadap SSRF:
# tanpa daftar ini user bisa mengarahkan server ke jaringan internal.
DEFAULT_ALLOWED_DOMAINS = (
    "youtube.com,youtu.be,music.youtube.com,"
    "vimeo.com,dailymotion.com,soundcloud.com,"
    "tiktok.com,instagram.com,twitter.com,x.com,facebook.com"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    download_dir: Path = Path("./downloads")

    # Batas sumber daya. Semua job yang melewati batas ini ditolak,
    # bukan dipotong -- lebih baik gagal cepat daripada disk penuh.
    file_ttl_seconds: int = 7200
    max_duration_seconds: int = 3600
    max_filesize_mb: int = 1024
    job_timeout_seconds: int = 900
    min_free_disk_mb: int = 2048

    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 3600

    # Dipisah koma. Subdomain otomatis ikut (mis. "m.youtube.com" cocok
    # dengan "youtube.com").
    allowed_domains: str = DEFAULT_ALLOWED_DOMAINS

    # Opsional, untuk menembus bot-check YouTube di IP datacenter.
    # Lihat README bagian "Kalau kena 'Sign in to confirm you're not a bot'".
    proxy: Optional[str] = None
    cookies_file: Optional[Path] = None

    @property
    def allowed_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()]

    @property
    def max_filesize_bytes(self) -> int:
        return self.max_filesize_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
