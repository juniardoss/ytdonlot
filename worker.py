"""Worker RQ. Jalankan minimal satu proses ini di samping API."""

from rq import Queue, Worker

from app.config import settings
from app.jobs import get_rq_redis


def main() -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    connection = get_rq_redis()
    queue = Queue("downloads", connection=connection)
    Worker([queue], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
