"""Validasi URL sebelum menyentuh yt-dlp.

Semua input user berhenti di sini dulu. yt-dlp bisa membuka skema selain
http (file://, ftp://) dan bisa diarahkan ke alamat internal, jadi
penyaringan dilakukan sebelum URL diteruskan ke extractor.
"""

import ipaddress
from urllib.parse import urlparse, urlunparse

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = {"http", "https"}


class UrlValidationError(ValueError):
    """URL ditolak sebelum masuk antrean."""


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _domain_allowed(host: str, allowed_domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def validate_url(raw: str, allowed_domains: list[str]) -> str:
    """Kembalikan URL yang sudah dinormalisasi, atau lempar UrlValidationError."""
    url = (raw or "").strip()
    if not url:
        raise UrlValidationError("URL tidak boleh kosong.")
    if len(url) > MAX_URL_LENGTH:
        raise UrlValidationError("URL terlalu panjang.")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UrlValidationError("Hanya URL http:// atau https:// yang diterima.")

    host = (parsed.hostname or "").lower()
    if not host:
        raise UrlValidationError("URL tidak memiliki hostname.")
    # IP literal ditolak: itu jalur paling mudah menuju 127.0.0.1,
    # jaringan privat, atau endpoint metadata cloud (169.254.169.254).
    if _is_ip_literal(host):
        raise UrlValidationError("Alamat IP langsung tidak diizinkan.")
    if not _domain_allowed(host, allowed_domains):
        raise UrlValidationError(f"Domain '{host}' tidak ada di daftar yang diizinkan.")

    # Rakit ulang tanpa userinfo (user:pass@) dan tanpa fragment.
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunparse(
        (parsed.scheme.lower(), netloc, parsed.path, parsed.params, parsed.query, "")
    )
