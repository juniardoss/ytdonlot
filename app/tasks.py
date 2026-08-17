"""Pekerjaan download yang dijalankan worker RQ.

Fungsi di sini TIDAK pernah dipanggil dari request HTTP secara langsung.
Download bisa makan beberapa menit; kalau dijalankan di dalam request,
koneksi timeout dan server tumbang saat beberapa user datang bersamaan.
"""

import shutil
import time
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError, match_filter_func

from app.config import settings
from app.formats import get_preset
from app.jobs import (
    STATUS_DONE,
    STATUS_DOWNLOADING,
    STATUS_ERROR,
    update_job,
)


class InsufficientDiskSpace(Exception):
    pass


def _job_dir(job_id: str) -> Path:
    return settings.download_dir / job_id


def _check_disk_space() -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    free_mb = shutil.disk_usage(settings.download_dir).free / (1024 * 1024)
    if free_mb < settings.min_free_disk_mb:
        raise InsufficientDiskSpace(
            f"Ruang disk tersisa {free_mb:.0f} MB, minimum {settings.min_free_disk_mb} MB."
        )


def _make_progress_hook(job_id: str):
    last_push = {"t": 0.0}

    def hook(d: dict) -> None:
        if d.get("status") != "downloading":
            return
        # Hook dipanggil ratusan kali per detik; batasi tulis ke Redis.
        now = time.monotonic()
        if now - last_push["t"] < 1.0:
            return
        last_push["t"] = now

        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        percent = (done / total * 100) if total else 0
        update_job(job_id, status=STATUS_DOWNLOADING, progress=round(percent, 1))

    return hook


def _build_opts(job_id: str, preset) -> dict:
    dest = _job_dir(job_id)
    dest.mkdir(parents=True, exist_ok=True)

    opts = {
        "format": preset.fmt,
        "paths": {"home": str(dest)},
        # Nama file dibatasi ke ASCII aman. Judul video bisa mengandung
        # "../" atau karakter yang merusak header Content-Disposition.
        "outtmpl": "%(title).150B.%(ext)s",
        "restrictfilenames": True,
        "windowsfilenames": True,
        # URL playlist hanya mengambil satu video, bukan 500.
        "noplaylist": True,
        "max_filesize": settings.max_filesize_bytes,
        "match_filter": match_filter_func(
            f"duration < {settings.max_duration_seconds}"
        ),
        "progress_hooks": [_make_progress_hook(job_id)],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "socket_timeout": 30,
        # Jangan biarkan yt-dlp menulis apa pun di luar folder job.
        "writethumbnail": False,
        "writeinfojson": False,
        "overwrites": True,
    }

    if preset.audio_only:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        opts["merge_output_format"] = preset.ext

    if settings.proxy:
        opts["proxy"] = settings.proxy
    if settings.cookies_file:
        opts["cookiefile"] = str(settings.cookies_file)

    return opts


def _resolve_output(info: dict, job_id: str) -> Path | None:
    """Cari file hasil akhir.

    Setelah merge atau ekstraksi audio, ekstensi berubah, jadi
    prepare_filename() tidak bisa dipercaya. yt-dlp menaruh path final di
    requested_downloads.
    """
    downloads = info.get("requested_downloads") or []
    for item in downloads:
        path = item.get("filepath")
        if path and Path(path).exists():
            return Path(path)

    # Cadangan: ambil file terbesar di folder job.
    files = [p for p in _job_dir(job_id).glob("*") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_size) if files else None


def run_download(job_id: str, url: str, preset_id: str) -> None:
    preset = get_preset(preset_id)
    if preset is None:
        update_job(job_id, status=STATUS_ERROR, error="Preset tidak dikenal.")
        return

    try:
        _check_disk_space()
        update_job(job_id, status=STATUS_DOWNLOADING, progress=0)

        with yt_dlp.YoutubeDL(_build_opts(job_id, preset)) as ydl:
            info = ydl.extract_info(url, download=True)

        if info is None:
            # match_filter menolak video (mis. durasi melebihi batas).
            raise DownloadError(
                f"Video dilewati: durasi melebihi batas "
                f"{settings.max_duration_seconds // 60} menit."
            )

        output = _resolve_output(info, job_id)
        if output is None:
            raise DownloadError("Download selesai tetapi file tidak ditemukan.")

        update_job(
            job_id,
            status=STATUS_DONE,
            progress=100,
            title=info.get("title") or "",
            filename=output.name,
            filesize=output.stat().st_size,
        )

    except InsufficientDiskSpace as exc:
        _fail(job_id, "Server sedang kehabisan ruang penyimpanan. Coba lagi nanti.", exc)
    except DownloadError as exc:
        _fail(job_id, _friendly_error(str(exc)), exc)
    except Exception as exc:  # noqa: BLE001 - job tidak boleh mematikan worker
        _fail(job_id, "Terjadi kesalahan tak terduga saat memproses video.", exc)


def _fail(job_id: str, message: str, exc: Exception) -> None:
    # Pesan teknis tetap masuk log worker, tapi tidak dikirim ke browser:
    # output yt-dlp bisa membocorkan path server dan konfigurasi proxy.
    print(f"[job {job_id}] gagal: {exc!r}", flush=True)
    update_job(job_id, status=STATUS_ERROR, error=message)
    shutil.rmtree(_job_dir(job_id), ignore_errors=True)


def _friendly_error(raw: str) -> str:
    lowered = raw.lower()
    if "sign in to confirm" in lowered or "bot" in lowered:
        return (
            "Situs sumber menolak permintaan dari server ini (deteksi bot). "
            "Lihat README bagian proxy/cookies."
        )
    if "video unavailable" in lowered or "private" in lowered:
        return "Video tidak tersedia, privat, atau sudah dihapus."
    if "unsupported url" in lowered:
        return "URL ini tidak didukung oleh extractor yang tersedia."
    if "file is larger" in lowered or "max_filesize" in lowered:
        return f"Ukuran file melebihi batas {settings.max_filesize_mb} MB."
    if "copyright" in lowered or "blocked" in lowered:
        return "Konten diblokir di wilayah server ini."
    return "Gagal mengunduh video. Coba URL lain atau periksa kembali tautannya."
