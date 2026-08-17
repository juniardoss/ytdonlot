"""Penyapu file kedaluwarsa.

Tanpa proses ini disk akan penuh dalam hitungan hari. Jalankan sebagai
container/service tersendiri, atau lewat cron.
"""

import shutil
import time

from app.config import settings

SWEEP_INTERVAL_SECONDS = 300


def sweep_once() -> int:
    root = settings.download_dir
    if not root.exists():
        return 0

    cutoff = time.time() - settings.file_ttl_seconds
    removed = 0
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError as exc:
            print(f"[cleanup] lewati {entry.name}: {exc}", flush=True)
    return removed


def main() -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"[cleanup] mulai, TTL {settings.file_ttl_seconds}s, "
        f"interval {SWEEP_INTERVAL_SECONDS}s",
        flush=True,
    )
    while True:
        removed = sweep_once()
        if removed:
            print(f"[cleanup] hapus {removed} folder job", flush=True)
        time.sleep(SWEEP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
